from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from collections import OrderedDict

from ...application.gateways.local_article_gateway import LocalArticleGateway
from ...application.usecases.load_local_article_segment_usecase import (
    LoadLocalArticleSegmentUseCase,
)
from ...models.dto.local_article import LocalArticleCatalogItem, LocalArticleSegment
from ...workers.base_worker import BaseWorker


class LocalArticleAdapter(QObject):
    """本地长文 Qt 适配层。"""

    localArticlesLoaded = Signal(list)
    localArticlesLoadFailed = Signal(str)
    localArticleSegmentLoaded = Signal(dict)
    localArticleSegmentLoadFailed = Signal(str)
    localArticleLoadingChanged = Signal()
    localArticleDeleted = Signal(bool, str)  # (success, message)
    localArticleRenamed = Signal(bool, str)  # (success, message)
    localArticlePreviewLoaded = Signal(str)  # content text

    def __init__(
        self,
        gateway: LocalArticleGateway,
        load_segment_usecase: LoadLocalArticleSegmentUseCase,
    ):
        super().__init__()
        self._gateway = gateway
        self._load_segment_usecase = load_segment_usecase
        self._thread_pool = QThreadPool.globalInstance()
        self._local_article_loading = False
        self._request_generation = 0
        self._preview_request_generation = 0
        self._preview_active_worker = None
        self._current_preview_article_id: str = ""
        self._active_worker = None
        # 预览内容缓存：keyed by article_id，上限 50 条，避免重复读文件
        self._preview_cache: OrderedDict[str, str] = OrderedDict()
        self._PREVIEW_CACHE_MAX = 50

    def _set_loading(self, loading: bool) -> None:
        if self._local_article_loading != loading:
            self._local_article_loading = loading
            self.localArticleLoadingChanged.emit()

    def _next_request_generation(self) -> int:
        self._request_generation += 1
        return self._request_generation

    def clear_active(self) -> None:
        """失效当前仍在后台运行的本地长文请求。"""
        self._next_request_generation()
        self._active_worker = None
        self._set_loading(False)

    @staticmethod
    def _catalog_item_to_dict(item: LocalArticleCatalogItem) -> dict:
        return {
            "articleId": item.article_id,
            "title": item.title,
            "path": item.path,
            "charCount": item.char_count,
            "modifiedTimestamp": item.modified_timestamp,
            "isBundled": item.is_bundled,
        }

    @staticmethod
    def _segment_to_dict(segment: LocalArticleSegment) -> dict:
        return {
            "articleId": segment.article_id,
            "title": segment.title,
            "content": segment.content,
            "index": segment.index,
            "total": segment.total,
        }

    def _list_articles(self) -> list[dict]:
        return [
            self._catalog_item_to_dict(item) for item in self._gateway.list_articles()
        ]

    def get_full_article_content(self, article_id: str) -> str:
        """返回指定文章的完整文本内容。"""
        return self._gateway.load_content(article_id)

    def get_article_title(self, article_id: str) -> str:
        """返回指定文章的标题。"""
        return self._gateway.get_article(article_id).title

    def resolve_article_path(self, article_id: str) -> str | None:
        """返回指定文章的文件绝对路径。"""
        return self._gateway.resolve_article_path(article_id)

    def _load_segment(
        self,
        article_id: str,
        segment_index: int,
        segment_size: int,
    ) -> dict:
        segment = self._load_segment_usecase.load_segment(
            article_id,
            segment_index=segment_index,
            segment_size=segment_size,
        )
        return self._segment_to_dict(segment)

    def _on_articles_loaded(
        self, request_generation: int, articles: list[dict]
    ) -> None:
        if request_generation != self._request_generation:
            return
        self.localArticlesLoaded.emit(articles)

    def _on_articles_load_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._request_generation:
            return
        self.localArticlesLoadFailed.emit(message)

    def _on_segment_loaded(self, request_generation: int, payload: dict) -> None:
        if request_generation != self._request_generation:
            return
        self.localArticleSegmentLoaded.emit(payload)

    def _on_segment_load_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._request_generation:
            return
        self.localArticleSegmentLoadFailed.emit(message)

    def _on_worker_finished(self, request_generation: int) -> None:
        if request_generation != self._request_generation:
            return
        self._active_worker = None
        self._set_loading(False)

    @Slot()
    def loadLocalArticles(self) -> None:
        if self._local_article_loading:
            return
        self._set_loading(True)
        request_generation = self._next_request_generation()
        worker = BaseWorker(
            task=self._list_articles,
            error_prefix="加载本地长文列表失败",
        )
        worker.signals.succeeded.connect(
            lambda articles, gen=request_generation: self._on_articles_loaded(
                gen, articles
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=request_generation: self._on_articles_load_failed(
                gen, message
            )
        )
        worker.signals.finished.connect(
            lambda gen=request_generation: self._on_worker_finished(gen)
        )
        self._active_worker = worker
        self._thread_pool.start(worker)

    @Slot(str, int, int)
    def loadLocalArticleSegment(
        self,
        article_id: str,
        segment_index: int,
        segment_size: int,
    ) -> None:
        if self._local_article_loading:
            return
        self._set_loading(True)
        request_generation = self._next_request_generation()
        worker = BaseWorker(
            task=lambda: self._load_segment(article_id, segment_index, segment_size),
            error_prefix="加载本地长文片段失败",
        )
        worker.signals.succeeded.connect(
            lambda payload, gen=request_generation: self._on_segment_loaded(
                gen, payload
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=request_generation: self._on_segment_load_failed(
                gen, message
            )
        )
        worker.signals.finished.connect(
            lambda gen=request_generation: self._on_worker_finished(gen)
        )
        self._active_worker = worker
        self._thread_pool.start(worker)

    @property
    def local_article_loading(self) -> bool:
        return self._local_article_loading

    @Slot(str)
    def deleteArticle(self, article_id: str) -> None:
        def _do_delete() -> bool:
            return self._gateway.delete_article(article_id)

        worker = BaseWorker(task=_do_delete, error_prefix="删除文章失败")
        worker.signals.succeeded.connect(
            lambda _: self.localArticleDeleted.emit(True, "文章已删除")
        )
        worker.signals.failed.connect(
            lambda msg: self.localArticleDeleted.emit(False, msg)
        )
        self._thread_pool.start(worker)

    @Slot(str)
    def loadLocalArticlePreview(self, article_id: str) -> None:
        """异步加载本地文章全文供预览卡片展示。

        优先使用内存缓存，减少重复读文件。
        缓存上限 50 条，超出时驱逐最久未访问的条目。

        安全设计：
        - 使用 _preview_request_generation 代际守卫丢弃过期回调
        - 跟踪当前 active worker，新请求到来时断开旧 worker 的信号连接
          （防止 thread pool 中堆积的 worker 完成后密集发射信号击穿 Qt 事件循环）
        - worker.setAutoDelete(True) 确保 worker 完成后立即释放
        """
        # 缓存命中
        if article_id in self._preview_cache:
            self._preview_cache.move_to_end(article_id)
            self.localArticlePreviewLoaded.emit(self._preview_cache[article_id])
            return

        self._preview_request_generation += 1
        request_generation = self._preview_request_generation
        self._current_preview_article_id = article_id

        # 断开上一个 worker 的所有信号连接
        if self._preview_active_worker is not None:
            try:
                self._preview_active_worker.signals.succeeded.disconnect()
            except TypeError:
                pass  # 没有连接时忽略
            try:
                self._preview_active_worker.signals.failed.disconnect()
            except TypeError:
                pass
            self._preview_active_worker = None

        def _do_load() -> str:
            try:
                return self.get_full_article_content(article_id)
            except Exception:
                return ""

        worker = BaseWorker(task=_do_load, error_prefix="加载文章预览失败")
        worker.setAutoDelete(True)
        worker.signals.succeeded.connect(
            lambda content, gen=request_generation: self._on_preview_loaded(
                gen, content
            )
        )
        worker.signals.failed.connect(
            lambda msg, gen=request_generation: self._on_preview_failed(gen, msg)
        )
        self._preview_active_worker = worker
        self._thread_pool.start(worker)

    def _on_preview_loaded(self, request_generation: int, content: str) -> None:
        if request_generation != self._preview_request_generation:
            return
        # 写入缓存
        article_id = self._current_preview_article_id
        if article_id:
            self._preview_cache[article_id] = content
            self._preview_cache.move_to_end(article_id)
            if len(self._preview_cache) > self._PREVIEW_CACHE_MAX:
                self._preview_cache.popitem(last=False)
        self.localArticlePreviewLoaded.emit(content)

    def _on_preview_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._preview_request_generation:
            return
        # 预览加载失败时发出空内容，让 QML 仍可更新状态
        self.localArticlePreviewLoaded.emit("")

    @Slot(str, str)
    def renameArticle(self, article_id: str, new_title: str) -> None:
        def _do_rename() -> bool:
            return self._gateway.rename_article(article_id, new_title)

        worker = BaseWorker(task=_do_rename, error_prefix="重命名失败")
        worker.signals.succeeded.connect(
            lambda _: self.localArticleRenamed.emit(True, "重命名成功")
        )
        worker.signals.failed.connect(
            lambda msg: self.localArticleRenamed.emit(False, msg)
        )
        self._thread_pool.start(worker)
