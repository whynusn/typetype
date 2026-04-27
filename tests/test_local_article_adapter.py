from unittest.mock import MagicMock

from src.backend.models.dto.local_article import (
    LocalArticleCatalogItem,
    LocalArticleSegment,
)


class DummyThreadPool:
    def __init__(self) -> None:
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter():
    from src.backend.presentation.adapters.local_article_adapter import (
        LocalArticleAdapter,
    )

    gateway = MagicMock()
    usecase = MagicMock()
    adapter = LocalArticleAdapter(gateway=gateway, load_segment_usecase=usecase)
    pool = DummyThreadPool()
    adapter._thread_pool = pool
    return adapter, gateway, usecase, pool


def test_load_local_articles_enqueues_worker_and_emits_catalog_payload():
    adapter, gateway, _, pool = _build_adapter()
    gateway.list_articles.return_value = [
        LocalArticleCatalogItem(
            article_id="a1",
            title="长文",
            path="/tmp/a1.txt",
            char_count=123,
            modified_timestamp=1710000000.0,
        )
    ]
    loaded: list[list[dict]] = []
    states: list[bool] = []
    adapter.localArticlesLoaded.connect(loaded.append)
    adapter.localArticleLoadingChanged.connect(
        lambda: states.append(adapter.local_article_loading)
    )

    adapter.loadLocalArticles()

    assert len(pool.started_workers) == 1
    assert adapter.local_article_loading is True
    pool.started_workers[0].run()

    assert loaded == [
        [
            {
                "articleId": "a1",
                "title": "长文",
                "path": "/tmp/a1.txt",
                "charCount": 123,
                "modifiedTimestamp": 1710000000.0,
            }
        ]
    ]
    assert adapter.local_article_loading is False
    assert states == [True, False]


def test_load_local_article_segment_enqueues_worker_and_emits_segment_payload():
    adapter, _, usecase, pool = _build_adapter()
    usecase.load_segment.return_value = LocalArticleSegment(
        article_id="a1",
        title="长文",
        content="片段内容",
        index=2,
        total=5,
    )
    loaded: list[dict] = []
    adapter.localArticleSegmentLoaded.connect(loaded.append)

    adapter.loadLocalArticleSegment("a1", 2, 500)

    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()

    usecase.load_segment.assert_called_once_with(
        "a1",
        segment_index=2,
        segment_size=500,
    )
    assert loaded == [
        {
            "articleId": "a1",
            "title": "长文",
            "content": "片段内容",
            "index": 2,
            "total": 5,
        }
    ]


def test_local_article_failures_clear_loading_and_emit_failure_signal():
    adapter, gateway, _, pool = _build_adapter()
    gateway.list_articles.side_effect = RuntimeError("boom")
    failures: list[str] = []
    adapter.localArticlesLoadFailed.connect(failures.append)

    adapter.loadLocalArticles()
    pool.started_workers[0].run()

    assert adapter.local_article_loading is False
    assert failures == ["加载本地长文列表失败：boom"]


def test_clear_active_invalidates_pending_segment_worker():
    adapter, _, usecase, pool = _build_adapter()
    usecase.load_segment.return_value = LocalArticleSegment(
        article_id="a1",
        title="长文",
        content="旧片段",
        index=1,
        total=2,
    )
    loaded: list[dict] = []
    adapter.localArticleSegmentLoaded.connect(loaded.append)

    adapter.loadLocalArticleSegment("a1", 1, 500)
    adapter.clear_active()
    pool.started_workers[0].run()

    assert adapter.local_article_loading is False
    assert loaded == []
