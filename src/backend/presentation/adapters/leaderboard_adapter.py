"""排行榜适配层 - Qt 信号管理。"""

from collections import OrderedDict
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...config.runtime_config import RuntimeConfig
from ...application.gateways.leaderboard_gateway import LeaderboardGateway
from ...models.dto.text_catalog_item import TextCatalogItem
from ...utils.logger import log_info, log_warning
from ...workers.leaderboard_worker import LeaderboardWorker
from ...workers.text_content_worker import TextContentWorker
from ...workers.text_list_worker import TextListWorker


class LeaderboardAdapter(QObject):
    """排行榜 Qt 适配层。

    职责：
    - Qt 信号管理
    - 线程协调（异步加载排行榜）
    - 错误回传
    """

    # 信号定义
    leaderboardLoaded = Signal(dict)  # 包含 text_info, leaderboard, total
    leaderboardLoadFailed = Signal(str)
    leaderboardLoadingChanged = Signal()

    catalogLoaded = Signal(list)  # list of {key, label} dicts
    catalogLoadFailed = Signal(str)
    catalogLoadingChanged = Signal()

    textListLoaded = Signal(list)  # list of text summary dicts
    textListLoadFailed = Signal(str)
    textListLoadingChanged = Signal()

    def __init__(
        self,
        leaderboard_gateway: LeaderboardGateway,
        runtime_config: RuntimeConfig,
        registry_provider=None,
    ):
        super().__init__()
        self._leaderboard_gateway = leaderboard_gateway
        self._registry_provider = registry_provider
        self._runtime_config = runtime_config
        self._thread_pool = QThreadPool.globalInstance()
        self._loading = False
        self._text_list_loading = False
        self._catalog_loading = False
        self._catalog_cache: list | None = None
        self._current_text_list_request: int = 0
        self._catalog_request_generation: int = 0
        self._preview_request_generation = 0
        self._preview_active_worker = None
        # 内容缓存：keyed by text_id，上限 50 条，避免重复选择同一文本时重复请求网络
        self._content_cache: OrderedDict[int, dict] = OrderedDict()
        self._CONTENT_CACHE_MAX = 50
        # 后台 worker 引用集：防止跨线程信号传递中 Python GC 回收 worker 的 QObject
        self._submit_workers: set = set()

    def _init_registry_provider(self) -> None:
        """运行时根据当前配置延迟创建 OttTextProvider。

        用户在设置页面填写 registry URL 时，registry_provider 尚未创建
        （启动时 URL 为空 → container.py 中 else None），此处按需创建。
        """
        primary_url = self._runtime_config.registry.primary_url
        log_info(
            f"[LeaderboardAdapter] _init_registry_provider: primary_url={primary_url!r}"
        )
        if not primary_url:
            log_info(
                "[LeaderboardAdapter] _init_registry_provider: primary_url 为空，跳过"
            )
            return
        try:
            from ...integration.ott_text_provider import OttTextProvider
            from ...config.app_paths import registry_cache_dir
            import httpx

            self._registry_provider = OttTextProvider(
                config=self._runtime_config.registry,
                cache_dir=registry_cache_dir(),
                http_client=httpx.Client(timeout=10.0, trust_env=False),
            )
            log_info(
                f"[LeaderboardAdapter] _init_registry_provider: 创建成功，primary_url={primary_url}"
            )
        except Exception as e:
            log_warning(f"[LeaderboardAdapter] 延迟创建 registry provider 失败: {e}")

    def _set_loading(self, loading: bool) -> None:
        if self._loading != loading:
            self._loading = loading
            self.leaderboardLoadingChanged.emit()

    def _set_text_list_loading(self, loading: bool) -> None:
        if self._text_list_loading != loading:
            self._text_list_loading = loading
            self.textListLoadingChanged.emit()

    def _set_catalog_loading(self, loading: bool) -> None:
        if self._catalog_loading != loading:
            self._catalog_loading = loading
            self.catalogLoadingChanged.emit()

    def _on_leaderboard_loaded(self, data: dict[str, Any]) -> None:
        """处理排行榜加载成功。"""
        self._set_loading(False)
        self.leaderboardLoaded.emit(data)

    def _on_leaderboard_load_failed(self, message: str) -> None:
        """处理排行榜加载失败。"""
        self._set_loading(False)
        self.leaderboardLoadFailed.emit(message)

    @Slot(str)
    def loadLeaderboard(self, source_key: str) -> None:
        """加载指定来源的排行榜。

        Args:
            source_key: 文本来源标识，如 "jisubei"
        """
        if self._loading:
            return

        self._set_loading(True)
        worker = LeaderboardWorker(
            leaderboard_gateway=self._leaderboard_gateway,
            source_key=source_key,
        )
        worker.signals.succeeded.connect(self._on_leaderboard_loaded)
        worker.signals.failed.connect(self._on_leaderboard_load_failed)
        self._thread_pool.start(worker)

    @Slot(int)
    def loadLeaderboardByTextId(self, text_id: int) -> None:
        """按 text_id 直接加载排行榜。

        Args:
            text_id: 文本 ID
        """
        if self._loading:
            return

        self._set_loading(True)
        worker = LeaderboardWorker(
            leaderboard_gateway=self._leaderboard_gateway,
            text_id=text_id,
        )
        worker.signals.succeeded.connect(self._on_leaderboard_loaded)
        worker.signals.failed.connect(self._on_leaderboard_load_failed)
        self._thread_pool.start(worker)

    @Slot()
    def loadCatalog(self) -> None:
        """加载文本来源目录（优先开源文库，fallback Leaderboard API）。

        如果缓存存在，直接使用缓存避免重复请求。
        """
        # 运行时确保 registry provider 已初始化（应对启动时 URL 为空
        # 后经设置页面配置的情况）
        if self._registry_provider is None:
            log_info(
                "[LeaderboardAdapter] loadCatalog: _registry_provider 为 None，尝试初始化"
            )
            self._init_registry_provider()
        if self._registry_provider is not None:
            log_info("[LeaderboardAdapter] loadCatalog: 使用 registry provider")
        else:
            log_info(
                "[LeaderboardAdapter] loadCatalog: registry provider 不可用，fallback 到 server API"
            )

        if self._catalog_cache is not None:
            self.catalogLoaded.emit(self._catalog_cache)
            return

        if self._catalog_loading:
            return  # 防止连续页面切换导致并发 worker 堆积

        self._set_catalog_loading(True)
        self._catalog_request_generation += 1
        request_generation = self._catalog_request_generation
        from ...workers.catalog_worker import CatalogWorker

        worker = CatalogWorker(
            leaderboard_gateway=self._leaderboard_gateway,
            registry_provider=self._registry_provider,
        )
        worker.signals.succeeded.connect(
            lambda data, gen=request_generation: self._on_catalog_loaded_gen(gen, data)
        )
        worker.signals.failed.connect(
            lambda msg, gen=request_generation: self._on_catalog_load_failed_gen(
                gen, msg
            )
        )
        self._thread_pool.start(worker)

    def loadRegistryEntries(self) -> None:
        """加载开源文库（OTT）聚合的全部条目（扁平列表，含预载内容）。"""
        if self._registry_provider is None:
            self._init_registry_provider()
        if self._registry_provider is None:
            self._on_catalog_load_failed("注册表文本源未配置")
            return

        self._set_catalog_loading(True)
        self._catalog_request_generation += 1
        request_generation = self._catalog_request_generation

        def _fetch() -> list[dict]:
            return self._registry_provider.fetch_all_entries()

        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=_fetch, error_prefix="加载开源文库条目失败")
        worker.setAutoDelete(True)
        worker.signals.succeeded.connect(
            lambda entries, gen=request_generation: self._on_entries_loaded(
                gen, entries
            )
        )
        worker.signals.failed.connect(
            lambda msg, gen=request_generation: self._on_catalog_load_failed_gen(
                gen, msg
            )
        )
        worker.signals.finished.connect(lambda: self._release_submit_worker(worker))
        self._submit_workers.add(worker)
        self._thread_pool.start(worker)

    def _on_entries_loaded(self, request_generation: int, entries: list[dict]) -> None:
        if request_generation != self._catalog_request_generation:
            return
        self._set_catalog_loading(False)
        self.catalogLoaded.emit(entries)

    def _on_catalog_loaded_gen(
        self, request_generation: int, catalog: list[dict]
    ) -> None:
        if request_generation != self._catalog_request_generation:
            return
        self._on_catalog_loaded(catalog)

    def _on_catalog_loaded(self, catalog: list[dict]) -> None:
        """处理目录加载成功。"""
        self._set_catalog_loading(False)
        # 转换为 TextCatalogItem 列表更新到 RuntimeConfig 供异步回查兜底使用
        catalog_items = [
            TextCatalogItem(
                id=int(item.get("id", 0)),
                source_key=item.get("sourceKey", ""),
                label=item.get("label", ""),
                description=item.get("category", ""),
                category=item.get("category", ""),
                update_freq=item.get("updateFreq", ""),
                has_ranking=True,  # ponytail: static till server returns has_ranking
            )
            for item in catalog
        ]
        self._runtime_config.update_catalog(catalog_items)

        # 透传所有 QML 需要的字段
        options = [
            {
                "key": item.get("sourceKey", ""),
                "label": item.get("label", ""),
                "description": item.get("description", ""),
                "charCount": item.get("charCount", 0),
                "category": item.get("category", ""),
                "updateFreq": item.get("updateFreq", ""),
            }
            for item in catalog
            if item.get("sourceKey")
        ]
        # 仅缓存非空目录，避免因一次空结果导致后续请求永久走缓存
        if options:
            self._catalog_cache = options
        self.catalogLoaded.emit(options)

    def _on_catalog_load_failed(self, message: str) -> None:
        """处理目录加载失败。"""
        self._set_catalog_loading(False)
        self.catalogLoadFailed.emit(message)

    def _on_catalog_load_failed_gen(
        self, request_generation: int, message: str
    ) -> None:
        if request_generation != self._catalog_request_generation:
            return
        self._on_catalog_load_failed(message)

    @Slot()
    def refreshCatalog(self) -> None:
        """清除缓存并重新从服务端加载文本来源目录。
        同时清除 OttTextProvider 的磁盘缓存，确保 URL 变更后不走旧缓存。
        """
        self._catalog_cache = None
        # 清除 registry 磁盘缓存
        if self._registry_provider is not None:
            self._registry_provider.clear_cache()
        self.loadCatalog()

    @Slot(str)
    def loadTextList(self, source_key: str) -> None:
        """加载来源下的文本列表。

        使用请求 ID 追踪，丢弃过期响应（解决快速切换来源时的竞态条件）。
        """
        self._current_text_list_request += 1
        request_id = self._current_text_list_request

        self._set_text_list_loading(True)
        worker = TextListWorker(
            leaderboard_gateway=self._leaderboard_gateway,
            source_key=source_key,
        )
        worker.signals.succeeded.connect(
            lambda data: self._on_text_list_loaded(data, request_id)
        )
        worker.signals.failed.connect(
            lambda msg: self._on_text_list_failed(msg, request_id)
        )
        self._thread_pool.start(worker)

    def _on_text_list_loaded(self, data: dict[str, Any], request_id: int) -> None:
        """处理文本列表加载成功。丢弃过期请求的响应。"""
        if request_id != self._current_text_list_request:
            return
        self._set_text_list_loading(False)
        self.textListLoaded.emit(data.get("texts", []))

    def _on_text_list_failed(self, message: str, request_id: int) -> None:
        """处理文本列表加载失败。丢弃过期请求的响应。"""
        if request_id != self._current_text_list_request:
            return
        self._set_text_list_loading(False)
        self.textListLoadFailed.emit(message)

    @property
    def loading(self) -> bool:
        return self._loading

    def get_text_content_by_id(self, text_id: int, callback) -> None:
        """按文本 ID 异步获取完整内容。

        优先使用内存缓存，减少重复网络请求。
        缓存上限 50 条，超出时驱逐最久未访问的条目。

        Args:
            text_id: 文本 ID
            callback: 成功回调，接收 dict 参数 (含 content, title)
        """
        # 缓存命中：move_to_end 维持 LRU 顺序，直接回调
        if text_id in self._content_cache:
            self._content_cache.move_to_end(text_id)
            callback(self._content_cache[text_id])
            return

        self._preview_request_generation += 1
        request_generation = self._preview_request_generation

        # 断开上一个 worker 的所有信号连接
        if self._preview_active_worker is not None:
            try:
                self._preview_active_worker.signals.succeeded.disconnect()
            except TypeError:
                pass
            try:
                self._preview_active_worker.signals.failed.disconnect()
            except TypeError:
                pass
            self._preview_active_worker = None

        worker = TextContentWorker(
            leaderboard_gateway=self._leaderboard_gateway, text_id=text_id
        )
        worker.setAutoDelete(True)
        worker.signals.succeeded.connect(
            lambda data, gen=request_generation, tid=text_id: (
                self._on_text_content_loaded(gen, tid, data, callback)
            )
        )
        worker.signals.failed.connect(
            lambda msg, gen=request_generation: self._on_text_content_failed(gen, msg)
        )
        self._preview_active_worker = worker
        self._thread_pool.start(worker)

    def _on_text_content_loaded(
        self, request_generation: int, text_id: int, data: dict, callback
    ) -> None:
        if request_generation != self._preview_request_generation:
            return
        # 写入缓存（LRU 淘汰）
        self._content_cache[text_id] = data
        self._content_cache.move_to_end(text_id)
        if len(self._content_cache) > self._CONTENT_CACHE_MAX:
            self._content_cache.popitem(last=False)
        callback(data)

    def _on_text_content_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._preview_request_generation:
            return
        log_warning(f"[LeaderboardAdapter] 获取文本内容失败: error={message}")

    @property
    def text_list_loading(self) -> bool:
        return self._text_list_loading

    @property
    def catalog_loading(self) -> bool:
        return self._catalog_loading

    def fetch_registry_text(self, source_key: str):
        """从开源文库获取单篇文本内容。返回 (text_id, content, title, entries) 或 raise。"""
        if self._registry_provider is None:
            raise RuntimeError("注册表文本源未配置")
        fetched = self._registry_provider.fetch_text_by_key(source_key)
        if fetched is None:
            raise RuntimeError(f"无法获取注册表文本({source_key})")
        return (
            fetched.text_id or 0,
            fetched.content or "",
            fetched.title or "",
            fetched.entries or [],
            {
                "source_key": fetched.source_key,
                "entry_id": fetched.entry_id,
                "revision_id": fetched.revision_id,
                "content_mode": fetched.content_mode,
                "segment_count": fetched.segment_count,
                "segment_size_hint": fetched.segment_size_hint,
                "content_hash": fetched.content_hash,
            },
        )

    def fetch_ott_entry_text(self, entry_id: str):
        """Fetch one OTT Core v1 inline entry by stable entry_id."""
        if self._registry_provider is None:
            raise RuntimeError("OTT 文本源未配置")
        fetched = self._registry_provider.fetch_text_by_entry_id(entry_id)
        if fetched is None or not fetched.content:
            raise RuntimeError(f"无法获取 OTT 文本({entry_id})")
        return (
            fetched.text_id or 0,
            fetched.content or "",
            fetched.title or "",
            fetched.entries or [],
            {
                "source_key": fetched.source_key,
                "entry_id": fetched.entry_id,
                "revision_id": fetched.revision_id,
                "content_mode": fetched.content_mode,
                "segment_count": fetched.segment_count,
                "segment_size_hint": fetched.segment_size_hint,
                "content_hash": fetched.content_hash,
            },
        )

    def submit_to_thread_pool(self, fn, on_result, on_error):
        """将 callable 提交到后台线程池执行，结果回调到主线程。

        保持对 worker 的引用直到完成，防止 worker 的 QObject 在
        跨线程信号传递过程中被 Python GC 回收导致 C++ 层内存损坏。
        """
        from ...workers.base_worker import BaseWorker

        worker = BaseWorker(task=fn, error_prefix="操作失败")
        worker.setAutoDelete(True)
        worker.signals.succeeded.connect(on_result)
        worker.signals.failed.connect(on_error)
        worker.signals.finished.connect(lambda: self._release_submit_worker(worker))
        self._submit_workers.add(worker)
        self._thread_pool.start(worker)
        return self._text_list_loading

    def _release_submit_worker(self, worker) -> None:
        self._submit_workers.discard(worker)
