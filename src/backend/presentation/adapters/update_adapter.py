"""OTA 更新适配层（ADR-014 决策 5/6）。

职责：
- 手动/自动更新检查（后台 Worker，节流由 UpdateWorker 负责）
- 匹配当前平台的下载资产，经直链 + 配置镜像逐个尝试下载
- sha256 校验由 UpdateChecker.download 保证；校验失败立即丢弃换下一个源
- 下载解压到临时目录后调用平台 updater 脚本替换安装目录并重启
- 暴露给 Bridge 的信号：checkFinished / downloadProgress / statusChanged

与 Lane E（update_checker.py）的接口约定（已对齐）：
- ``UpdateChecker.check_for_update() -> UpdateInfo | None``，UpdateInfo 含
  ``version`` 与 ``assets``（每条含 name/url/sha256）
- ``UpdateChecker.download(url, sha256, dest: Path) -> bool``
- ``UpdateChecker.build_download_candidates(release_tag, asset_name, mirrors=None)
   -> list[str]``（直链 + 镜像 URL 列表；sha256 需从 UpdateInfo.assets 取）
- ``UpdateChecker(download_mirrors=[...])`` 构造注入镜像列表
- 已知限制：Lane E 的 ``download`` 暂不支持进度回调，进度信号恒为 0
  （QML 侧显示 indeterminate）。若后续新增 ``on_progress`` 参数，
  UpdateAdapter 已探测签名并自动透传。
"""

from __future__ import annotations

import inspect
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, Signal

from ...utils.logger import log_warning
from ...workers.base_worker import BaseWorker
from ...workers.update_worker import UpdateWorker

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig

# 各平台资产文件名（build-release.yml 产出）
_PLATFORM_ASSETS: dict[str, str] = {
    "linux": "typetype-linux-amd64.tar.gz",
    "win32": "typetype-windows-amd64.zip",
    "darwin": "typetype-macos.zip",
}

# 状态词汇表（statusChanged 载荷；QML 侧据此驱动状态机）
STATUS_DOWNLOADING = "downloading"
STATUS_EXTRACTING = "extracting"
STATUS_INSTALLING = "installing"
STATUS_DONE = "done"


def _resolve_app_version() -> str:
    """运行时版本解析：src.backend.version.APP_VERSION → 包元数据 → 兜底。"""
    try:
        from src.backend.version import APP_VERSION

        if APP_VERSION:
            return str(APP_VERSION)
    except ImportError:
        pass
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("typetype")
    except Exception:
        pass
    return "0.1.0"


class UpdateAdapter(QObject):
    """OTA 更新检查与下载安装适配层。"""

    checkFinished = Signal(bool, str, str)  # (available, version, error_message)
    downloadProgress = Signal(int)  # 0-100 百分比
    statusChanged = Signal(str)  # 状态文本（见 STATUS_* 词汇表）

    def __init__(
        self,
        update_checker,
        runtime_config: "RuntimeConfig | None" = None,
    ) -> None:
        super().__init__()
        self._update_checker = update_checker
        self._runtime_config = runtime_config
        self._thread_pool = QThreadPool.globalInstance()
        self._checking = False
        self._downloading = False
        self._manual = False
        self._available_version = ""
        self._current_version = _resolve_app_version()
        # Lane E 的 download 是否支持 on_progress 回调（探测一次，避免每次抛 TypeError）
        self._download_supports_progress = self._probe_progress_support()

    def _probe_progress_support(self) -> bool:
        try:
            sig = inspect.signature(self._update_checker.download)
            return "on_progress" in sig.parameters
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_version(self) -> str:
        return self._current_version

    @property
    def available_version(self) -> str:
        return self._available_version

    # ------------------------------------------------------------------
    # 检查
    # ------------------------------------------------------------------

    def check_now(self) -> None:
        """手动触发检查（强制，绕过节流）。"""
        if self._checking:
            return
        self._manual = True
        self._start_check(force=True)

    def start_auto_check(self) -> None:
        """启动时后台自动检查（失败静默）。"""
        if self._checking:
            return
        self._manual = False
        self._start_check(force=False)

    def _start_check(self, force: bool) -> None:
        interval = (
            self._runtime_config.update.check_interval_hours
            if self._runtime_config
            else 24
        )
        worker = UpdateWorker(
            update_checker=self._update_checker,
            check_interval_hours=interval,
            force=force,
        )
        worker.signals.checkFinished.connect(self._on_check_finished)
        worker.signals.finished.connect(self._on_check_worker_finished)
        self._checking = True
        # 清掉上一次的状态文本（检查期间 UI 显示按钮禁用态）
        self.statusChanged.emit("")
        self._thread_pool.start(worker)

    def _on_check_finished(self, available: bool, version: str, error: str) -> None:
        # 自动检查失败静默：不向 UI 抛错误（worker 已 log_warning）
        if error and not self._manual:
            self.checkFinished.emit(False, "", "")
            return
        self._available_version = version if available else ""
        self.checkFinished.emit(available, version, error)

    def _on_check_worker_finished(self) -> None:
        self._checking = False

    # ------------------------------------------------------------------
    # 下载与安装
    # ------------------------------------------------------------------

    def download_and_install(self, version: str) -> None:
        """下载并安装指定版本（后台）。"""
        if self._downloading:
            return
        self._downloading = True
        self.statusChanged.emit(STATUS_DOWNLOADING)

        def _task() -> bool:
            self._do_download_and_install(version)
            return True

        worker = BaseWorker(task=_task, error_prefix="下载更新失败")
        worker.signals.failed.connect(self._on_download_error)
        worker.signals.finished.connect(self._on_download_worker_finished)
        self._thread_pool.start(worker)

    def _on_download_error(self, message: str) -> None:
        self.statusChanged.emit(f"error:{message}")

    def _on_download_worker_finished(self) -> None:
        self._downloading = False

    def _do_download_and_install(self, version: str) -> None:
        """同步核心：下载 → 解压 → 调用 updater。测试可直接调用。"""
        asset_name = self._platform_asset_name()
        sha256 = self._asset_sha256(version, asset_name)
        urls = self._build_candidates(version, asset_name)
        if not urls:
            raise RuntimeError("无可用的下载源")

        download_dir = Path(tempfile.mkdtemp(prefix="typetype-download-"))
        stage_dir = Path(tempfile.mkdtemp(prefix="typetype-stage-"))
        dest = download_dir / asset_name

        archive_path = self._download_with_fallback(urls, sha256, dest)
        self.statusChanged.emit(STATUS_EXTRACTING)
        self._extract_archive(archive_path, stage_dir)

        install_dir = self._install_dir()
        self.statusChanged.emit(STATUS_INSTALLING)
        self._run_updater(install_dir, stage_dir)
        self.statusChanged.emit(STATUS_DONE)

    def _platform_asset_name(self) -> str:
        """返回当前平台资产文件名；平台无产物时抛错。"""
        for prefix, asset in _PLATFORM_ASSETS.items():
            if sys.platform.startswith(prefix) or sys.platform == prefix:
                return asset
        raise RuntimeError("当前平台暂无可更新产物")

    def _asset_sha256(self, version: str, asset_name: str) -> str:
        """从最新 UpdateInfo.assets 取目标资产的 sha256。

        重新执行一次 check_for_update()（走 GitHub API → 已验签 manifest
        降级链），取匹配资产的 sha256。API 不返回 sha256 时会尝试 manifest
        补全（Lane E 行为）；仍为空则 download() 会拒绝（返回 False），
        走 fallback 链直至报错。
        """
        try:
            info = self._update_checker.check_for_update()
        except Exception as e:  # noqa: BLE001 - 取不到 sha256 按空处理
            log_warning(f"[UpdateAdapter] 获取更新清单失败: {e}")
            return ""
        if info is None:
            return ""
        for asset in info.assets or []:
            if asset.get("name") == asset_name:
                return str(asset.get("sha256") or "")
        return ""

    def _mirrors(self) -> list[str]:
        if self._runtime_config:
            return list(self._runtime_config.update.mirrors or [])
        return []

    def _build_candidates(self, version: str, asset_name: str) -> list[str]:
        """调用 Lane E 的 build_download_candidates。

        配置镜像列表为空时传 None → Lane E 使用其内置默认镜像
        （DEFAULT_DOWNLOAD_MIRRORS，ghproxy 系），保证开箱可用。
        """
        mirrors = self._mirrors() or None
        raw = self._update_checker.build_download_candidates(
            version, asset_name, mirrors
        )
        return [str(url) for url in raw or [] if url]

    def _download_with_fallback(self, urls: list[str], sha256: str, dest: Path) -> Path:
        """按序尝试直链 + 镜像；校验失败/异常则换下一个源。"""
        for url in urls:
            try:
                ok = self._download(url, sha256, dest)
            except Exception as e:  # noqa: BLE001 - 换下一个源
                log_warning(f"[UpdateAdapter] 下载失败 {url}: {e}")
                continue
            if ok:
                return dest
            log_warning(f"[UpdateAdapter] sha256 校验失败，丢弃: {url}")
        raise RuntimeError("所有下载源均失败")

    def _download(self, url: str, sha256: str, dest: Path) -> bool:
        """调用 UpdateChecker.download；若支持进度回调则透传。"""
        if self._download_supports_progress:
            return self._update_checker.download(
                url, sha256, dest, on_progress=self._on_progress
            )
        return self._update_checker.download(url, sha256, dest)

    def _on_progress(self, *args) -> None:
        """UpdateChecker 进度回调 → downloadProgress(percent)。

        兼容两种回调形态：on_progress(percent) 或 on_progress(downloaded, total)。
        """
        try:
            if len(args) >= 2 and args[1]:
                percent = int(int(args[0]) * 100 // int(args[1]))
            elif args:
                percent = int(args[0])
            else:
                percent = 0
        except (TypeError, ValueError):
            percent = 0
        self.downloadProgress.emit(max(0, min(100, percent)))

    def _extract_archive(self, archive_path: Path, stage_dir: Path) -> None:
        """解压归档到 stage 目录（tar.gz / zip 两态）。"""
        if archive_path.name.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(stage_dir)
        else:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(stage_dir)

    def _install_dir(self) -> Path:
        """安装目录 = 当前运行可执行文件所在目录。"""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(sys.argv[0]).resolve().parent

    def _run_updater(self, install_dir: Path, stage_dir: Path) -> None:
        """后台 detach 调用平台 updater 脚本（返回后由 updater 自行替换并重启）。"""
        script = self._updater_script_path()
        args = [str(script), str(install_dir), str(stage_dir)]
        kwargs: dict = {}
        if sys.platform == "win32":
            creationflags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creationflags = (
                    subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                )
            kwargs["creationflags"] = creationflags
            kwargs["stdin"] = kwargs["stdout"] = kwargs["stderr"] = subprocess.DEVNULL
        else:
            kwargs["start_new_session"] = True
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        subprocess.Popen(args, **kwargs)

    def _updater_script_path(self) -> Path:
        root = Path(__file__).resolve().parents[4]
        updater_dir = root / "resources" / "updater"
        if sys.platform == "win32":
            return updater_dir / "updater.bat"
        return updater_dir / "updater.sh"

    def dismiss(self) -> None:
        """清除更新提示状态。"""
        self._available_version = ""
        self.statusChanged.emit("")
