from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.gateways.local_article_gateway import LocalArticleGateway
from ...application.usecases.load_local_article_segment_usecase import (
    LoadLocalArticleSegmentUseCase,
)
from ...models.dto.local_article import LocalArticleCatalogItem, LocalArticleSegment
from ...workers.local_article_worker import LocalArticleWorker


class LocalArticleAdapter(QObject):
    """本地长文 Qt 适配层。"""

    localArticlesLoaded = Signal(list)
    localArticlesLoadFailed = Signal(str)
    localArticleSegmentLoaded = Signal(dict)
    localArticleSegmentLoadFailed = Signal(str)
    localArticleLoadingChanged = Signal()

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
        self._active_worker = None

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
        worker = LocalArticleWorker(
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
        worker = LocalArticleWorker(
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
