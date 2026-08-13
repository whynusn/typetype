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

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig
    from ...integration.ott_federation_provider import OttFederationProvider
    from ...integration.ott_repo_manifest import RepoManifestCache
    from ...application.services.snapshot_catalog_service import SnapshotCatalogService


class RegistryAdapter(QObject):
    """OTT Repo 联邦目录适配层。"""

    # 信号
    reposChanged = Signal(list)  # list of repo summary dicts
    reposLoadFailed = Signal(str)
    reposLoadingChanged = Signal()

    entriesLoaded = Signal(list)  # list of entry dicts
    entriesLoadFailed = Signal(str)
    entriesLoadingChanged = Signal()

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
        """移除一条订阅并刷新列表。"""
        url = (url or "").strip().rstrip("/")
        try:
            removed = (
                self._runtime_config.remove_source_repo(url)
                if self._runtime_config is not None
                else False
            )
            if removed:
                self._manifest_cache.clear_cache(url)
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
    # 条目加载
    # ------------------------------------------------------------------

    @Slot()
    def loadAllEntries(self) -> None:
        """加载联邦聚合的全部条目（后台）。"""
        if self._entries_loading:
            return
        self._set_entries_loading(True)

        def _load() -> list[dict]:
            if self._catalog is not None:
                return self._catalog.refresh_and_list_all()
            return self._federation.list_all_entries()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_load, error_prefix="加载条目列表失败")
        worker.signals.succeeded.connect(self._on_entries_loaded)
        worker.signals.failed.connect(self._on_entries_load_failed)
        # 超时保护：15 秒后强制结束，防止网络请求卡死
        from PySide6.QtCore import QTimer

        def _timeout():
            if self._entries_loading:
                log_warning("[RegistryAdapter] loadAllEntries 超时")
                self._on_entries_load_failed("加载超时，请检查网络")

        QTimer.singleShot(15000, _timeout)
        self._thread_pool.start(worker)

    def _on_entries_loaded(self, entries: list[dict]) -> None:
        self._set_entries_loading(False)
        self.entriesLoaded.emit(entries)

    def _on_entries_load_failed(self, message: str) -> None:
        self._set_entries_loading(False)
        self.entriesLoadFailed.emit(message)

    def _set_entries_loading(self, loading: bool) -> None:
        if self._entries_loading != loading:
            self._entries_loading = loading
            self.entriesLoadingChanged.emit()

    @property
    def entries_loading(self) -> bool:
        return self._entries_loading

    # ------------------------------------------------------------------
    # 单源刷新（动态源 random 换新）
    # ------------------------------------------------------------------

    @Slot(str)
    def refreshSource(self, authority: str) -> None:
        """单源强制刷新（random 换新）并重发条目列表。"""
        if not authority:
            return
        if self._catalog is None:
            # 无 catalog（未装配）：退化为普通全量加载
            self._set_entries_loading(True)

            def _plain() -> list[dict]:
                return self._federation.list_all_entries()

            from ...workers.base_worker import BaseWorker

            worker = BaseWorker(task=_plain, error_prefix="刷新文本源失败")
            worker.signals.succeeded.connect(self._on_entries_loaded)
            worker.signals.failed.connect(self._on_entries_load_failed)
            self._thread_pool.start(worker)
            return
        self._set_entries_loading(True)

        def _refresh() -> list[dict]:
            self._catalog.refresh_source(authority)
            return self._catalog.refresh_and_list_all()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新文本源失败")
        worker.signals.succeeded.connect(self._on_entries_loaded)
        worker.signals.failed.connect(self._on_entries_load_failed)
        self._thread_pool.start(worker)

    @property
    def catalog(self) -> "SnapshotCatalogService | None":
        return self._catalog
