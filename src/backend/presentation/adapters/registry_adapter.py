"""OTT Repo 联邦目录适配层（OTT Repo 控制面）。

职责：
- 封装 OttFederationProvider + RepoManifestCache，提供订阅管理接口
- 暴露订阅列表（含 manifest 摘要）供 UI 展示
- 管理订阅的增删改、启用/禁用、手动刷新
- 加载联邦聚合的全部条目（ OttTextProvider 的入口点）

所有耗时操作（manifest 拉取、订阅列表含加载态）均走后台 Worker。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig
    from ...integration.ott_federation_provider import OttFederationProvider
    from ...integration.ott_repo_manifest import RepoManifestCache
    from ...application.services.snapshot_catalog_service import SnapshotCatalogService
    from ...workers.base_worker import BaseWorker

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
    refreshingAuthorityChanged = Signal()  # 源（authority）级刷新进行中（组头动画）
    refreshingAuthoritiesChanged = Signal()  # 并发源级刷新集合变化
    sourceStatusChanged = Signal(str, object)  # (authority, status dict)

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
        self._refreshing_authority = ""
        # 并发源级刷新集合：每个 authority 一份动画，不再被后点者覆盖。
        # 插入顺序即用户点击顺序；singular 属性保留最后者（兼容旧 QML）。
        self._refreshing_authorities: list[str] = []
        self._refreshing_authority_seqs: dict[str, int] = {}
        # 并发刷新序号：成功/失败回调用序号守卫，旧 worker 晚完成时不会
        # 清除新一次刷新的组头动画标记（单值标记，后者覆盖前者）。
        self._refresh_seq = 0
        self._refreshing_repo_seq = 0
        # 进行中的 worker 必须持有引用：QRunnable 交给 QThreadPool 后
        # Python wrapper（及其 WorkerSignals QObject）若被 GC，跨线程排队
        # 信号可能丢失（成功清标记的 lambda 不再执行 → 动画永转，实测）。
        self._active_workers: set["BaseWorker"] = set()
        # 手动刷新与后台 revalidate 各自独立硬超时：单发 QTimer 互不干扰，
        # 避免「源级刷新成功后，残留的 revalidate 定时器到点误报超时」。
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._revalidate_timer = QTimer(self)
        self._revalidate_timer.setSingleShot(True)
        self._revalidate_timer.timeout.connect(self._on_revalidate_timeout)

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

    @Slot(str, result="QVariantMap")
    def previewRepoManifest(self, url: str) -> dict:
        """预览 manifest（不订阅）：供添加订阅弹窗识别仓库/目录。"""
        try:
            return self._federation.preview_manifest(url)
        except Exception as e:
            log_warning(f"[RegistryAdapter] 预览 manifest 失败: {e}")
            return {"url": url, "error": "预览失败"}

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
        self._start_worker(worker)

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
        self._start_worker(worker)

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
        self._start_revalidate_timeout()  # 后台超时静默（保持快照视图）

        def _load() -> list[dict]:
            if self._catalog is not None:
                return self._catalog.refresh_and_list_all()
            return self._federation.list_all_entries()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_load, error_prefix="后台刷新条目失败")
        worker.signals.succeeded.connect(self._on_entries_revalidated)
        worker.signals.failed.connect(self._on_entries_revalidate_failed)
        self._start_worker(worker)

    def _on_entries_revalidated(self, entries: list[dict]) -> None:
        self._entries_revalidating = False
        # 原地更新为最新存储（快照视图已显示，不置 loading、不白屏）
        self.entriesLoaded.emit(entries)
        self._stop_revalidate_timeout_if_idle()

    def _on_entries_revalidate_failed(self, message: str) -> None:
        # 后台刷新失败不影响已显示的快照视图（保持当前存储），只记日志
        self._entries_revalidating = False
        log_warning(f"[RegistryAdapter] 后台条目刷新失败: {message}")
        self._stop_revalidate_timeout_if_idle()

    def _on_entries_loaded(self, entries: list[dict]) -> None:
        self._set_entries_loading(False)
        self.entriesLoaded.emit(entries)
        self._stop_refresh_timeout_if_idle()

    def _on_entries_load_failed(self, message: str) -> None:
        self._set_entries_loading(False)
        self.entriesLoadFailed.emit(message)
        self._stop_refresh_timeout_if_idle()

    # ------------------------------------------------------------------
    # Worker 生命周期（关键陷阱）：QRunnable 交给 QThreadPool 后必须继续
    # 持有 Python wrapper 引用，否则 wrapper（连同 WorkerSignals QObject）
    # 可能被 GC，跨线程排队的 succeeded/failed 信号会随机丢失——表现为
    # 「刷新成功文本已更新，但清标记的 lambda 没执行，动画永转」。
    # ------------------------------------------------------------------

    def _start_worker(self, worker: "BaseWorker") -> None:
        """持有引用地启动 worker；finished 后释放（跨线程信号交付完毕）。"""
        worker.setAutoDelete(False)
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda done=worker: self._release_worker(done))
        self._thread_pool.start(worker)

    def _release_worker(self, worker: "BaseWorker") -> None:
        self._active_workers.discard(worker)

    def _next_refresh_seq(self) -> int:
        """并发刷新序号：晚完成的前一次刷新不得清除新一轮刷新的标记。"""
        self._refresh_seq += 1
        return self._refresh_seq

    def _clear_refreshing_repo_if(self, seq: int) -> None:
        if self._refreshing_repo_seq == seq:
            self._set_refreshing_repo("")

    def _clear_refreshing_authority_if(self, authority: str, seq: int) -> None:
        self._end_refreshing_authority(authority, seq)

    # ------------------------------------------------------------------
    # 刷新硬超时兜底（2026-08-14 恢复）：worker 卡死（网络 hang 等）时
    # 只清理状态 + 提示，不等待 worker 线程；worker 之后完成仍会正常
    # 重发列表（无害）。手动刷新与后台 revalidate 使用两个独立定时器：
    # 手动操作完成/失败即停表；陈旧超时经状态检查直接忽略。
    # ------------------------------------------------------------------

    def _start_refresh_timeout(self) -> None:
        """启动（重启）手动条目物化/刷新硬超时（loading/组头动画兜底）。"""
        self._refresh_timer.start(_ENTRIES_REFRESH_TIMEOUT_S * 1000)

    def _stop_refresh_timeout_if_idle(self) -> None:
        """所有手动刷新状态都已清空 → 停止超时表（防止陈旧超时误报）。"""
        if (
            not self._entries_loading
            and not self._refreshing_repo
            and not self._refreshing_authorities
        ):
            self._refresh_timer.stop()

    def _start_revalidate_timeout(self) -> None:
        """启动后台 revalidate 硬超时（静默清理，不发错误信号）。"""
        self._revalidate_timer.start(_ENTRIES_REFRESH_TIMEOUT_S * 1000)

    def _stop_revalidate_timeout_if_idle(self) -> None:
        if not self._entries_revalidating:
            self._revalidate_timer.stop()

    def _on_refresh_timeout(self) -> None:
        # 手动刷新操作均已结束 → 本超时是陈旧定时器（worker 提前完成）→ 忽略
        if (
            not self._entries_loading
            and not self._refreshing_repo
            and not self._refreshing_authorities
        ):
            return
        log_warning(
            f"[RegistryAdapter] 条目刷新超时（>{_ENTRIES_REFRESH_TIMEOUT_S}s），已清理状态"
        )
        self._set_refreshing_repo("")
        self._clear_all_refreshing_authorities()
        self._set_entries_loading(False)
        self.entriesLoadFailed.emit("刷新超时，请检查网络")

    def _on_revalidate_timeout(self) -> None:
        # 后台 revalidate 超时：静默清理状态（保持已显示的快照视图）
        if not self._entries_revalidating:
            return
        log_warning(
            f"[RegistryAdapter] 后台条目刷新超时"
            f"（>{_ENTRIES_REFRESH_TIMEOUT_S}s），保持快照视图"
        )
        self._entries_revalidating = False

    def _set_entries_loading(self, loading: bool) -> None:
        if self._entries_loading != loading:
            self._entries_loading = loading
            self.entriesLoadingChanged.emit()

    @property
    def entries_loading(self) -> bool:
        return self._entries_loading

    def _set_refreshing_repo(self, repo_id: str) -> None:
        """标记正在刷新的订阅源（repo_id；空串 = 无）——源组头动画驱动。

        单值即可：并发刷新时后点者覆盖前者标记（前者的 worker 仍会
        完成并重发列表，只是动画提前结束），不做集合管理。
        """
        if self._refreshing_repo != repo_id:
            self._refreshing_repo = repo_id
            self.refreshingRepoChanged.emit()

    @property
    def refreshing_repo(self) -> str:
        """当前正在刷新的订阅源 repo_id（'' = 无）。"""
        return self._refreshing_repo

    def _set_refreshing_authority(self, authority: str) -> None:
        """兼容旧调用：空串清空全部源级动画；非空按单值语义设置。

        新代码请使用 ``_begin/_end_refreshing_authority`` 支持并发集合。
        """
        if authority:
            self._begin_refreshing_authority(authority, self._next_refresh_seq())
        else:
            self._clear_all_refreshing_authorities()

    def _begin_refreshing_authority(self, authority: str, seq: int) -> None:
        """把一个 authority 加入并发刷新集合并设为 singular 最新值。"""
        if not authority:
            return
        changed = False
        if authority not in self._refreshing_authorities:
            self._refreshing_authorities.append(authority)
            changed = True
        self._refreshing_authority_seqs[authority] = seq
        if self._refreshing_authority != authority:
            self._refreshing_authority = authority
            self.refreshingAuthorityChanged.emit()
        if changed:
            self.refreshingAuthoritiesChanged.emit()

    def _end_refreshing_authority(self, authority: str, seq: int) -> None:
        """序号匹配才移除（旧 worker 晚完成不清新一轮动画）。"""
        if not authority or authority not in self._refreshing_authorities:
            return
        if self._refreshing_authority_seqs.get(authority) != seq:
            return
        self._refreshing_authority_seqs.pop(authority, None)
        self._refreshing_authorities.remove(authority)
        self.refreshingAuthoritiesChanged.emit()
        self._refreshing_authority = (
            self._refreshing_authorities[-1] if self._refreshing_authorities else ""
        )
        self.refreshingAuthorityChanged.emit()

    def _clear_all_refreshing_authorities(self) -> None:
        if not self._refreshing_authorities and not self._refreshing_authority:
            return
        self._refreshing_authorities.clear()
        self._refreshing_authority_seqs.clear()
        self._refreshing_authority = ""
        self.refreshingAuthoritiesChanged.emit()
        self.refreshingAuthorityChanged.emit()

    @property
    def refreshing_authority(self) -> str:
        """最近一个正在刷新的源 authority（'' = 无；兼容旧绑定）。"""
        return self._refreshing_authority

    @property
    def refreshing_authorities(self) -> list[str]:
        """所有正在刷新的源 authority 列表（并发动画各播一份）。"""
        return list(self._refreshing_authorities)

    # ------------------------------------------------------------------
    # 源（authority）级刷新：组头按源粒度换新（条目按 _authority 动态归组）
    # ------------------------------------------------------------------

    @Slot(str)
    def refreshSourceEntries(self, authority: str) -> None:
        """源（authority）级强制刷新并重发条目列表。

        只物化该 authority 一个源，其他源零调用；不置列表级 loading，
        只标记 refreshing_authority 供对应源组头播放一份动画；列表保持
        可交互。刷新完成后检查物化统计：全部失败 → 明确报错（当前显示
        缓存快照），部分失败 → 日志提示。
        """
        if not authority:
            return
        if self._catalog is None:
            # 无 catalog（未装配）：退化为普通全量加载（列表级 loading）
            self._set_entries_loading(True)
            self._start_refresh_timeout()

            def _plain() -> list[dict]:
                return self._federation.refresh_source(authority)

            from ...workers.base_worker import BaseWorker

            worker = BaseWorker(task=_plain, error_prefix="刷新文本源失败")
            worker.signals.succeeded.connect(self._on_entries_loaded)
            worker.signals.failed.connect(self._on_entries_load_failed)
            self._start_worker(worker)
            return
        seq = self._next_refresh_seq()
        self._begin_refreshing_authority(authority, seq)
        self._start_refresh_timeout()

        def _refresh() -> dict:
            self._catalog.refresh_source(authority)
            return {
                "entries": self._catalog.list_cached(),
                "ok": list(self._catalog.last_refresh_ok),
                "failed": list(self._catalog.last_refresh_failed),
            }

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新文本源失败")
        worker.signals.succeeded.connect(
            lambda result, seq=seq, authority=authority: (
                self._on_source_entries_refreshed(seq, authority, result)
            )
        )
        worker.signals.failed.connect(
            lambda message, seq=seq, authority=authority: (
                self._on_source_entries_refresh_failed(seq, authority, message)
            )
        )
        self._start_worker(worker)

    def _on_source_entries_refreshed(
        self, seq: int, authority: str, result: dict
    ) -> None:
        """源级刷新成功：重发列表 + 源状态 + 按序号清组头动画标记。

        单个连接处理（不把「清标记」拆成第二个 succeeded 连接）：首槽内
        嵌套发射 entriesLoaded 时，PySide6 对同一信号后续连接的分发存在
        丢连接竞态；拆成两个连接会随机丢「清标记」槽 → 动画永转。
        """
        try:
            self._on_entries_refreshed(result, authority=authority)
        finally:
            self._clear_refreshing_authority_if(authority, seq)
            self._stop_refresh_timeout_if_idle()

    def _on_source_entries_refresh_failed(
        self, seq: int, authority: str, message: str
    ) -> None:
        """源级刷新失败：只发源状态（不盖整列表）+ 按序号清动画标记。"""
        try:
            self._set_entries_loading(False)
            self.sourceStatusChanged.emit(
                authority,
                {
                    "state": "failed",
                    "message": message,
                    "checked_at": time.time(),
                },
            )
        finally:
            self._clear_refreshing_authority_if(authority, seq)
            self._stop_refresh_timeout_if_idle()

    # ------------------------------------------------------------------
    # 订阅源（repo）级刷新（旧粒度，QML 已改源级；保留后端能力）
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
            self._start_worker(worker)
            return
        seq = self._next_refresh_seq()
        self._refreshing_repo_seq = seq
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
        worker.signals.succeeded.connect(
            lambda entries, seq=seq: self._on_repo_entries_refreshed(seq, entries)
        )
        worker.signals.failed.connect(
            lambda message, seq=seq: self._on_repo_entries_refresh_failed(seq, message)
        )
        self._start_worker(worker)

    def _on_repo_entries_refreshed(self, seq: int, entries: list[dict]) -> None:
        """repo 级刷新成功：重发列表 + 按序号清组头动画标记（不拆连接）。"""
        try:
            self._on_entries_loaded(entries)
        finally:
            self._clear_refreshing_repo_if(seq)
            self._stop_refresh_timeout_if_idle()

    def _on_repo_entries_refresh_failed(self, seq: int, message: str) -> None:
        """repo 级刷新失败：报错 + 按序号清组头动画标记（不拆连接）。"""
        try:
            self._on_entries_load_failed(message)
        finally:
            self._clear_refreshing_repo_if(seq)
            self._stop_refresh_timeout_if_idle()

    @Slot()
    def refreshAllSources(self) -> None:
        """全部源强制刷新（随机源抽新 + 静态源换新）并重发条目列表。

        完成后检查物化统计：全部失败 → 明确报错（当前显示的是缓存快照，
        刷新并未成功）；部分失败 → 日志提示。
        """
        if self._entries_loading:
            return
        # 列表级刷新接管一切：清除可能残留的源组头动画标记
        self._set_refreshing_repo("")
        self._clear_all_refreshing_authorities()
        self._set_entries_loading(True)
        self._start_refresh_timeout()

        def _refresh() -> dict:
            if self._catalog is not None:
                entries = self._catalog.refresh_and_list_all(force=True)
                return {
                    "entries": entries,
                    "ok": list(self._catalog.last_refresh_ok),
                    "failed": list(self._catalog.last_refresh_failed),
                }
            return {
                "entries": self._federation.list_all_entries(force=True),
                "ok": list(self._federation._last_list_ok),
                "failed": list(self._federation._last_list_failed),
            }

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_refresh, error_prefix="刷新全部文本源失败")
        worker.signals.succeeded.connect(self._on_entries_refreshed)
        worker.signals.failed.connect(self._on_entries_load_failed)
        self._start_worker(worker)

    def _on_entries_refreshed(self, result: dict, *, authority: str = "") -> None:
        """手动刷新（源级/全部）完成：重发列表 + 按作用域失败反馈。

        断网/源不可用时物化失败但视图仍等于缓存快照（不收缩语义）——
        必须明确告知用户刷新未成功，否则会被误认为刷新成功。
        authority 非空 = 源级刷新：失败只发 sourceStatusChanged，
        **不发射全局 entriesLoadFailed**（否则 QML 会用错误页盖掉整列表）。
        """
        entries = result.get("entries") or []
        ok = result.get("ok") or []
        failed = result.get("failed") or []
        self._set_entries_loading(False)
        self.entriesLoaded.emit(entries)
        self._stop_refresh_timeout_if_idle()
        now = time.time()
        for name in ok:
            self.sourceStatusChanged.emit(
                name, {"state": "ok", "checked_at": now, "message": ""}
            )
        if not failed:
            return
        message = "刷新失败（网络不可达或源不可用），当前显示的是缓存快照"
        for name in failed:
            self.sourceStatusChanged.emit(
                name, {"state": "failed", "checked_at": now, "message": message}
            )
        if authority:
            # 源级作用域：错误只留在该源组头，列表保持可交互
            return
        if not ok:
            self.entriesLoadFailed.emit(message)
        else:
            log_warning(
                f"[RegistryAdapter] 部分源刷新失败: {', '.join(failed)}，"
                f"成功: {', '.join(ok) or '无'}"
            )

    @property
    def catalog(self) -> "SnapshotCatalogService | None":
        return self._catalog

    @property
    def source_statuses(self) -> dict:
        """per-authority 源健康状态（持久化快照；供 QML 初始化源组芯片）。"""
        if self._catalog is None:
            return {}
        try:
            return self._catalog.list_source_statuses()
        except Exception as e:
            log_warning(f"[RegistryAdapter] 读取源状态失败: {e}")
            return {}
