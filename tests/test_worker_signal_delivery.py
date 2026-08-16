"""Regression tests for cross-thread signal delivery via real QThreadPool.

Existing adapter tests use DummyThreadPool which calls worker.run()
synchronously. These tests verify signals actually arrive across thread
boundaries when dispatched through QThreadPool.globalInstance().

The adapter must keep a reference to the dispatched QRunnable (via
self._active_worker) so the Python wrapper — and its WorkerSignals
QObject — stay alive until the queued signal events are processed
by the main thread event loop.
"""

import time

from PySide6.QtCore import QCoreApplication, QThreadPool

from src.backend.workers.base_worker import BaseWorker


def _ensure_app() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(["test"])
    return app


def _spin_event_loop(app: QCoreApplication, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def test_base_worker_signals_arrive_via_real_threadpool() -> None:
    """Sanity: BaseWorker signals work across real QThreadPool."""
    app = _ensure_app()
    pool = QThreadPool.globalInstance()

    results: list[str] = []
    finished = [False]

    worker = BaseWorker(task=lambda: "hello", error_prefix="test")
    worker.signals.succeeded.connect(lambda val: results.append(val))
    worker.signals.finished.connect(lambda: finished.__setitem__(0, True))

    pool.start(worker)
    _spin_event_loop(app)

    assert finished[0], "worker.finished was never delivered"
    assert results == ["hello"]


def test_trainer_adapter_signals_arrive_via_real_threadpool() -> None:
    """TrainerAdapter using real QThreadPool — regression test."""
    from unittest.mock import MagicMock

    from src.backend.models.dto.trainer import TrainerCatalogItem
    from src.backend.presentation.adapters.trainer_adapter import TrainerAdapter

    app = _ensure_app()
    gateway = MagicMock()
    gateway.list_trainers.return_value = [
        TrainerCatalogItem(
            trainer_id="1.前500",
            title="前500",
            path="/tmp/t.txt",
            entry_count=500,
            modified_timestamp=1710000000.0,
        )
    ]
    adapter = TrainerAdapter(gateway=gateway, load_segment_usecase=MagicMock())
    adapter._thread_pool = QThreadPool.globalInstance()

    loaded: list[list[dict]] = []
    adapter.trainersLoaded.connect(loaded.append)

    adapter.loadTrainers()
    _spin_event_loop(app)

    assert len(loaded) == 1
    assert loaded[0][0]["trainerId"] == "1.前500"


def test_local_article_adapter_signals_arrive_via_real_threadpool() -> None:
    """LocalArticleAdapter using real QThreadPool — regression test."""
    from unittest.mock import MagicMock

    from src.backend.models.dto.local_article import LocalArticleCatalogItem
    from src.backend.presentation.adapters.local_article_adapter import (
        LocalArticleAdapter,
    )

    app = _ensure_app()
    gateway = MagicMock()
    gateway.list_articles.return_value = [
        LocalArticleCatalogItem(
            article_id="a1",
            title="长文",
            path="/tmp/a1.txt",
            char_count=123,
            modified_timestamp=1710000000.0,
        )
    ]
    adapter = LocalArticleAdapter(gateway=gateway, load_segment_usecase=MagicMock())
    adapter._thread_pool = QThreadPool.globalInstance()

    loaded: list[list[dict]] = []
    adapter.localArticlesLoaded.connect(loaded.append)

    adapter.loadLocalArticles()
    _spin_event_loop(app)

    assert len(loaded) == 1
    assert loaded[0][0]["articleId"] == "a1"


def test_registry_source_refresh_clears_spinner_via_real_threadpool() -> None:
    """RegistryAdapter 源级刷新跨线程信号必须完整送达（动画标记必清）。

    回归：worker 交给 QThreadPool 后 Python wrapper 被 GC，跨线程排队的
    第二个 succeeded 连接（清 refreshing_authority 的 lambda）随机丢失，
    表现为「文本已刷新但组头动画永转，直到 45s 超时」。
    """
    from unittest.mock import MagicMock

    from src.backend.presentation.adapters.registry_adapter import RegistryAdapter

    app = _ensure_app()
    catalog = MagicMock()
    catalog.list_cached.return_value = [{"entry_id": "e1", "_authority": "a1"}]
    catalog.last_refresh_ok = ["a1"]
    catalog.last_refresh_failed = []
    adapter = RegistryAdapter(
        federation=MagicMock(), manifest_cache=MagicMock(), catalog=catalog
    )
    adapter._thread_pool = QThreadPool.globalInstance()

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)

    adapter.refreshSourceEntries("a1")
    assert adapter.refreshing_authority == "a1"
    _spin_event_loop(app)

    assert loaded and loaded[-1][0]["entry_id"] == "e1"
    assert adapter.refreshing_authority == ""  # 成功即清，动画必须有结束态
    assert not adapter._active_workers  # finished 后释放 worker 引用
