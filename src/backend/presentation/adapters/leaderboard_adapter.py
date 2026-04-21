"""排行榜适配层 - Qt 信号管理。"""

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...config.runtime_config import RuntimeConfig
from ...application.gateways.leaderboard_gateway import LeaderboardGateway
from ...models.dto.text_catalog_item import TextCatalogItem
from ...workers.leaderboard_worker import LeaderboardWorker
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

    textListLoaded = Signal(list)  # list of text summary dicts
    textListLoadFailed = Signal(str)
    textListLoadingChanged = Signal()

    def __init__(
        self, leaderboard_gateway: LeaderboardGateway, runtime_config: RuntimeConfig
    ):
        super().__init__()
        self._leaderboard_gateway = leaderboard_gateway
        self._runtime_config = runtime_config
        self._thread_pool = QThreadPool.globalInstance()
        self._loading = False
        self._text_list_loading = False
        self._catalog_cache: list | None = None
        self._current_text_list_request: int = 0

    def _set_loading(self, loading: bool) -> None:
        if self._loading != loading:
            self._loading = loading
            self.leaderboardLoadingChanged.emit()

    def _set_text_list_loading(self, loading: bool) -> None:
        if self._text_list_loading != loading:
            self._text_list_loading = loading
            self.textListLoadingChanged.emit()

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
        """从服务端加载文本来源目录。

        如果缓存存在，直接使用缓存避免重复请求。
        """
        if self._catalog_cache is not None:
            self.catalogLoaded.emit(self._catalog_cache)
            return

        from ...workers.catalog_worker import CatalogWorker

        worker = CatalogWorker(leaderboard_gateway=self._leaderboard_gateway)
        worker.signals.succeeded.connect(self._on_catalog_loaded)
        worker.signals.failed.connect(self._on_catalog_load_failed)
        self._thread_pool.start(worker)

    def _on_catalog_loaded(self, catalog: list[dict]) -> None:
        """处理目录加载成功。"""
        # 转换为 TextCatalogItem 列表更新到 RuntimeConfig 供异步回查兜底使用
        catalog_items = [
            TextCatalogItem(
                id=int(item.get("id", 0)),
                text_id=item.get("sourceKey", ""),
                label=item.get("label", ""),
                description=item.get("category", ""),
                has_ranking=False,
            )
            for item in catalog
        ]
        self._runtime_config.update_catalog(catalog_items)

        # 转换服务端 TextSource 字段名 (sourceKey → key) 匹配 QML ComboBox
        options = [
            {"key": item.get("sourceKey", ""), "label": item.get("label", "")}
            for item in catalog
            if item.get("sourceKey")
        ]
        self._catalog_cache = options
        self.catalogLoaded.emit(options)

    def _on_catalog_load_failed(self, message: str) -> None:
        """处理目录加载失败。"""
        self.catalogLoadFailed.emit(message)

    @Slot()
    def refreshCatalog(self) -> None:
        """清除缓存并重新从服务端加载文本来源目录。"""
        self._catalog_cache = None
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

    @property
    def text_list_loading(self) -> bool:
        return self._text_list_loading
