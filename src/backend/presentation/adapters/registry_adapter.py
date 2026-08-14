"""OTT Repo 联邦目录适配层（OTT Repo 控制面）。

职责：
- 封装 OttFederationProvider + RepoManifestCache，提供订阅管理接口
- 暴露订阅列表（含 manifest 摘要）供 UI 展示
- 管理订阅的增删改、启用/禁用、手动刷新
- 加载联邦聚合的全部条目（ OttTextProvider 的入口点）

所有耗时操作（manifest 拉取、订阅列表含加载态）均走后台 Worker。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig
    from ...integration.ott_federation_provider import OttFederationProvider
    from ...integration.ott_repo_manifest import RepoManifestCache
    from ...application.services.snapshot_catalog_service import SnapshotCatalogService

# 条目物化/刷新硬超时（秒）：旧实现曾用 15s QTimer 兜底，重构时丢失——
# 网络请求虽然各有 timeout，但一个 worker 任务串行多请求/多页/脚本+条目
# 总时长可能很长，且某环节 hang（DNS 挂起等）时无兜底会导致 worker 永不
# 完成、loading/动画永转。超时只清理状态并提示，不等待 worker 线程。
_ENTRIES_REFRESH_TIMEOUT_S = 45


class RegistryAdapter(QObject):
    """OTT Repo 联邦目录适配层。"""

    # 信号
    reposChanged = Signal(list)  # list of repo summary dicts
    reposLoadFailed = Signal(str)
    reposLoadingChanged = Signal()

    entriesLoaded = Signal(list)  # list of entry dicts
    entriesLoadFailed = Signal(str)
    entriesLoadingChanged = Signal()
    refreshingRepoChanged = Signal()  # 订阅源（repo）级刷新进行中（组头动画）

    def __init__(
        self,
        federation: "OttFederationProvider",
        manifest_cache: "RepoManifestCache",
        runtime_config: "RuntimeConfig | None" = None,
        catalog: "SnapshotCatalogService | None" = None,
    ) -> None:
        super().__init__()
        self._federation = federation
        self._manifest_cache = manifest_cache
        # 订阅配置由 container.py 直接注入本适配器持有，
        # 不穿透 federation 的私有字段（ott_federation_provider 禁改）。
        self._runtime_config = runtime_config
        # 动态源快照目录（SnapshotCatalogService）：快照优先载入 + 单源刷新
        self._catalog = catalog
        self._thread_pool = QThreadPool.globalInstance()
        self._repos_loading = False
        self._entries_loading = False
        self._entries_revalidating = False
        self._refreshing_repo = ""
        # 刷新超时保护：单发 QTimer 每次操作重启；到点经状态检查区分陈旧超时
        self._refresh_timeout_quiet = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)

    # ------------------------------------------------------------------
    # 订阅管理
    # ------------------------------------------------------------------

    @Slot(result=list)
    def getRepos(self) -> list[dict]:
        """返回所有订阅的摘要（同步，manifest 优先走缓存）。"""
        try:
            return self._federation.list_repos()
        except Exception as e:
            log_warning(f"[RegistryAdapter] getRepos 失败: {e}")
            return []

    @Slot(str)
    def addRepo(self, url: str) -> None:
        """添加一条订阅并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        if not url:
            self.reposLoadFailed.emit("订阅地址不能为空")
            return
        if self._runtime_config is None:
            # 未注入 runtime_config：无法持久化，必须显式失败而不是静默 no-op
            self.reposLoadFailed.emit("配置系统未就绪，无法添加订阅")
            log_warning("[RegistryAdapter] addRepo 失败：runtime_config 未注入")
            return
        try:
            self._runtime_config.add_source_repo(url)
            log_info(f"[RegistryAdapter] 添加订阅: {url}")
            self.refreshRepos()
        except Exception as e:
            self.reposLoadFailed.emit(
                f"添加订阅失败：{GlobalExceptionHandler.handle(e)}"
            )

    @Slot(str)
    def removeRepo(self, url: str) -> None:
        """移除一条订阅（连带清理其快照残留）并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        try:
            # 先取该订阅的 repo_id（clients 缓存此刻仍含该 repo 的归属映射），
            # 再移除配置；随后清理其全部 authority 的快照目录（防孤儿残留）。
            repo_id = (
                self._federation.repo_id_of_url(url)
                if self._catalog is not None
                else ""
            )
            removed = (
                self._runtime_config.remove_source_repo(url)
                if self._runtime_config is not None
                else False
            )
            if removed:
                self._manifest_cache.clear_cache(url)
                if repo_id and self._catalog is not None:
                    self._catalog.remove_repo(repo_id)
                # 条目视图同步：删除后立即重发当前快照列表（该源条目已清）
                if self._catalog is not None:
                    try:
                        self.entriesLoaded.emit(self._catalog.list_cached())
                    except Exception:
                        pass
                log_info(f"[RegistryAdapter] 移除订阅: {url}")
            self.refreshRepos()
        except Exception as e:
            self.reposLoadFailed.emit(
                f"移除订阅失败：{GlobalExceptionHandler.handle(e)}"
            )

    @Slot(str, bool)
    def setRepoEnabled(self, url: str, enabled: bool) -> None:
        """启用/禁用一条订阅并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        try:
            if self._runtime_config is not None:
                self._runtime_config.set_source_repo_enabled(url, enabled)
            self.refreshRepos()
        except Exception as e:
            self.reposLoadFailed.emit(
                f"更新订阅失败：{GlobalExceptionHandler.handle(e)}"
            )

    @Slot(str)
    def confirmRepoTrust(self, url: str) -> None:
        """用户确认信任订阅（TOFU pending → verified）并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        try:
            if self._runtime_config is not None:
                self._runtime_config.confirm_source_repo_trust(url)
            log_info(f"[RegistryAdapter] 确认信任订阅: {url}")
            self.refreshRepos()
        except Exception as e:
            self.reposLoadFailed.emit(
                f"确认信任失败：{GlobalExceptionHandler.handle(e)}"
            )

    @Slot(str)
    def rejectRepoTrust(self, url: str) -> None:
        """用户拒绝信任订阅（TOFU pending → unverified，清空固定公钥）并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        try:
            if self._runtime_config is not None:
                self._runtime_config.reject_source_repo_trust(url)
            log_info(f"[RegistryAdapter] 拒绝信任订阅: {url}")
            self.refreshRepos()
        except Exception as e:
            self.reposLoadFailed.emit(
                f"拒绝信任失败：{GlobalExceptionHandler.handle(e)}"
            )

    @Slot(str)
    def refreshRepo(self, url: str) -> None:
        """强制刷新单条订阅的 manifest 并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        if not url:
            return
        self._set_repos_loading(True)

        def _refresh() -> list[dict]:
            repos = (
                self._runtime_config.source_repos.repos if self._runtime_config else []
            )
            for repo in repos:
                if repo.url == url:
                    self._manifest_cache.refresh_manifest(repo)
                    break
            return self._federation.list_repos()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新订阅失败")
        worker.signals.succeeded.connect(self._on_repos_loaded)
        worker.signals.failed.connect(self._on_repos_load_failed)
        self._thread_pool.start(worker)

    @Slot()
    def refreshRepos(self) -> None:
        """重新加载所有订阅的 manifest 摘要（后台）。"""
        if self._repos_loading:
            return
        self._set_repos_loading(True)

        def _load() -> list[dict]:
            return self._federation.list_repos()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_load, error_prefix="加载订阅列表失败")
        worker.signals.succeeded.connect(self._on_repos_loaded)
        worker.signals.failed.connect(self._on_repos_load_failed)
        self._thread_pool.start(worker)

    def _on_repos_loaded(self, repos: list[dict]) -> None:
        self._set_repos_loading(False)
        self.reposChanged.emit(repos)

    def _on_repos_load_failed(self, message: str) -> None:
        self._set_repos_loading(False)
        self.reposLoadFailed.emit(message)

    def _set_repos_loading(self, loading: bool) -> None:
        if self._repos_loading != loading:
            self._repos_loading = loading
            self.reposLoadingChanged.emit()

    @property
    def repos_loading(self) -> bool:
        return self._repos_loading

    # ------------------------------------------------------------------
    # 条目加载（进入开源文库：视图永远 = 当前快照存储，零网络）
    # ------------------------------------------------------------------

    @Slot()
    def loadFederatedEntries(self) -> None:
        """进入开源文库：同步显示当前全部已存快照（零网络、不白屏），
        随后后台重新物化过期源并原地更新列表。

        视图永远等于当前快照存储（每次查看都成立，非仅首屏）；存储新鲜度
        由后台 revalidate + RefreshScheduler + 过期/prune 机制维护，手动
        刷新（refreshAllSources / refreshSource）才强制换新。
        """
        # 1) 立即显示当前已存快照（无论何时查看都是「当前所有已存储快照」）
        try:
            if self._catalog is not None:
                entries = self._catalog.list_cached()
            else:
                entries = self._federation.list_all_entries()
        except Exception as e:
            log_warning(f"[RegistryAdapter] loadFederatedEntries 失败: {e}")
            self._on_entries_load_failed("读取缓存条目失败")
            return
        self._on_entries_loaded(entries or [])
        # 2) 后台非强制重新物化（仅 TTL 过期源重抓），完成后原地更新
        self._revalidate_entries()

    def _revalidate_entries(self) -> None:
        """后台重新物化过期源并原地更新列表（不置 loading、不白屏）。"""
        if self._entries_revalidating:
            return
        self._entries_revalidating = True
        self._start_refresh_timeout(quiet=True)  # 后台超时静默（保持快照视图）

        def _load() -> list[dict]:
            if self._catalog is not None:
                return self._catalog.refresh_and_list_all()
            return self._federation.list_all_entries()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_load, error_prefix="后台刷新条目失败")
        worker.signals.succeeded.connect(self._on_entries_revalidated)
        worker.signals.failed.connect(self._on_entries_revalidate_failed)
        self._thread_pool.start(worker)

    def _on_entries_revalidated(self, entries: list[dict]) -> None:
        self._entries_revalidating = False
        # 原地更新为最新存储（快照视图已显示，不置 loading、不白屏）
        self.entriesLoaded.emit(entries)

    def _on_entries_revalidate_failed(self, message: str) -> None:
        # 后台刷新失败不影响已显示的快照视图（保持当前存储），只记日志
        self._entries_revalidating = False
        log_warning(f"[RegistryAdapter] 后台条目刷新失败: {message}")

    def _on_entries_loaded(self, entries: list[dict]) -> None:
        self._set_entries_loading(False)
        self.entriesLoaded.emit(entries)

    def _on_entries_load_failed(self, message: str) -> None:
        self._set_entries_loading(False)
        self.entriesLoadFailed.emit(message)

    # ------------------------------------------------------------------
    # 刷新硬超时兜底（2026-08-14 恢复）：worker 卡死（网络 hang 等）时
    # 只清理状态 + 提示，不等待 worker 线程；worker 之后完成仍会正常
    # 重发列表（无害）。陈旧超时（操作已提前完成）经状态检查直接忽略。
    # ------------------------------------------------------------------

    def _start_refresh_timeout(self, quiet: bool = False) -> None:
        """启动（重启）条目物化/刷新硬超时。quiet：后台 revalidate（超时静默）。"""
        self._refresh_timeout_quiet = quiet
        self._refresh_timer.start(_ENTRIES_REFRESH_TIMEOUT_S * 1000)

    def _on_refresh_timeout(self) -> None:
        # 所有条目操作均已结束 → 本超时是陈旧定时器（worker 提前完成）→ 忽略
        if (
            not self._entries_loading
            and not self._refreshing_repo
            and not self._entries_revalidating
        ):
            return
        log_warning(
            f"[RegistryAdapter] 条目刷新超时（>{_ENTRIES_REFRESH_TIMEOUT_S}s），已清理状态"
        )
        quiet = self._refresh_timeout_quiet
        self._set_refreshing_repo("")
        self._set_entries_loading(False)
        self._entries_revalidating = False
        if not quiet:
            self.entriesLoadFailed.emit("刷新超时，请检查网络")

    def _set_entries_loading(self, loading: bool) -> None:
        if self._entries_loading != loading:
            self._entries_loading = loading
            self.entriesLoadingChanged.emit()

    @property
    def entries_loading(self) -> bool:
        return self._entries_loading

    def _set_refreshing_repo(self, repo_id: str) -> None:
        """标记正在刷新的订阅源（repo_id；空串 = 无）——源组头动画驱动。

        单值即可：并发 repo 刷新时后点者覆盖前者标记（前者的 worker 仍会
        完成并重发列表，只是动画提前结束），不做集合管理。
        """
        if self._refreshing_repo != repo_id:
            self._refreshing_repo = repo_id
            self.refreshingRepoChanged.emit()

    @property
    def refreshing_repo(self) -> str:
        """当前正在刷新的订阅源 repo_id（'' = 无）。"""
        return self._refreshing_repo

    # ------------------------------------------------------------------
    # 订阅源（repo）级刷新：组头按订阅源粒度换新（条目按 _repo_id 动态归组）
    # ------------------------------------------------------------------

    @Slot(str)
    def refreshRepoEntries(self, repo_id: str) -> None:
        """订阅源（repo）级强制刷新并重发条目列表。

        按组件层级作用域：repo 刷新**不置列表级 loading**（不覆盖整列表
        动画），只标记 refreshing_repo 供对应源组头播放一份动画；列表
        保持可交互，其他源组可继续点击。
        """
        if not repo_id:
            return
        if self._catalog is None:
            # 无 catalog（未装配）：退化为普通全量加载（列表级 loading）
            self._set_entries_loading(True)
            self._start_refresh_timeout()

            def _plain() -> list[dict]:
                return self._federation.list_all_entries()

            from ...workers.base_worker import BaseWorker

            worker = BaseWorker(task=_plain, error_prefix="刷新文本源失败")
            worker.signals.succeeded.connect(self._on_entries_loaded)
            worker.signals.failed.connect(self._on_entries_load_failed)
            self._thread_pool.start(worker)
            return
        self._set_refreshing_repo(repo_id)
        self._start_refresh_timeout()

        def _refresh() -> list[dict]:
            # 只物化该 repo 下的全部 authority（federation.authorities_of_repo），
            # 其他 repo 零调用；视图 = 当前全部已存快照（list_cached 纯读，
            # 绝不走 refresh_and_list_all——那会重物化其他 repo 并重置 freshness）。
            self._catalog.refresh_repo(repo_id)
            return self._catalog.list_cached()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新文本源失败")
        worker.signals.succeeded.connect(self._on_entries_loaded)
        worker.signals.succeeded.connect(
            lambda _entries: self._set_refreshing_repo("")
        )
        worker.signals.failed.connect(self._on_entries_load_failed)
        worker.signals.failed.connect(
            lambda _message: self._set_refreshing_repo("")
        )
        self._thread_pool.start(worker)

    @Slot()
    def refreshAllSources(self) -> None:
        """全部源强制刷新（随机源抽新 + 静态源换新）并重发条目列表。"""
        if self._entries_loading:
            return
        # 列表级刷新接管一切：清除可能残留的源组头动画标记
        self._set_refreshing_repo("")
        self._set_entries_loading(True)
        self._start_refresh_timeout()

        def _refresh() -> list[dict]:
            if self._catalog is not None:
                return self._catalog.refresh_and_list_all(force=True)
            return self._federation.list_all_entries(force=True)

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新全部文本源失败")
        worker.signals.succeeded.connect(self._on_entries_loaded)
        worker.signals.failed.connect(self._on_entries_load_failed)
        self._thread_pool.start(worker)

    @property
    def catalog(self) -> "SnapshotCatalogService | None":
        return self._catalog
