from unittest.mock import MagicMock

from src.backend.application.usecases.load_wenlai_text_usecase import WenlaiLoadResult
from src.backend.models.dto.wenlai_dto import WenlaiText
from src.backend.presentation.adapters.wenlai_adapter import WenlaiAdapter


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker):
        self.started_workers.append(worker)


def _build_adapter() -> tuple[WenlaiAdapter, MagicMock, MagicMock]:
    gateway = MagicMock()
    gateway.is_logged_in.return_value = False
    gateway.config.base_url = "https://example.test"
    gateway.config.length = 500
    gateway.config.difficulty_level = 0
    gateway.config.category = ""
    gateway.config.segment_mode = "manual"
    gateway.config.strict_length = False
    gateway.config.display_name = ""
    gateway.config.username = ""
    usecase = MagicMock()
    adapter = WenlaiAdapter(gateway=gateway, load_usecase=usecase)
    return adapter, gateway, usecase


def test_request_random_text_enqueues_worker():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.loadRandomText()

    assert len(thread_pool.started_workers) == 1
    assert adapter.text_loading is True


def test_duplicate_text_request_is_ignored_while_request_is_loading():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.loadRandomText()
    adapter.loadRandomText()

    assert len(thread_pool.started_workers) == 1


def test_adapter_emits_text_loaded_and_tracks_current_text():
    adapter, _, _ = _build_adapter()
    loaded: list[tuple[str, str]] = []
    adapter.textLoaded.connect(lambda text, title: loaded.append((text, title)))

    result = WenlaiLoadResult(
        text=WenlaiText(title="书", content="正文", book_id=1, sort_num=1)
    )
    adapter._on_text_loaded(result)

    assert loaded == [("正文", "书")]
    assert adapter.is_active is True
    assert adapter.current_text is not None


def test_stale_random_text_success_is_ignored_after_clear_active():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded: list[tuple[str, str]] = []
    adapter.textLoaded.connect(lambda text, title: loaded.append((text, title)))

    adapter.loadRandomText()
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()

    stale_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="旧文", content="旧正文", book_id=1, sort_num=1)
        )
    )

    assert loaded == []
    assert adapter.current_text is None
    assert adapter.is_active is False


def test_text_request_loading_clears_when_worker_finishes():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.loadRandomText()
    assert adapter.text_loading is True
    assert len(adapter._active_workers) == 1

    thread_pool.started_workers[0].signals.finished.emit()

    assert adapter.text_loading is False
    assert adapter._active_workers == set()


def test_text_request_timeout_clears_loading_and_ignores_late_success():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    failures: list[str] = []
    loaded: list[tuple[str, str]] = []
    adapter.loadFailed.connect(failures.append)
    adapter.textLoaded.connect(lambda text, title: loaded.append((text, title)))

    adapter.loadRandomText()
    stale_worker = thread_pool.started_workers[0]
    adapter._on_text_request_timeout(adapter._text_request_generation)
    adapter.loadRandomText()

    assert adapter.text_loading is True
    assert len(thread_pool.started_workers) == 2
    assert failures == ["晴发文请求超时，请稍后重试"]

    stale_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="旧文", content="旧正文", book_id=1, sort_num=1)
        )
    )

    assert loaded == []


def test_stale_random_text_success_is_ignored_after_new_text_request():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded: list[tuple[str, str]] = []
    adapter.textLoaded.connect(lambda text, title: loaded.append((text, title)))

    adapter.loadRandomText()
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()
    adapter.loadRandomText()
    active_worker = thread_pool.started_workers[1]

    stale_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="旧文", content="旧正文", book_id=1, sort_num=1)
        )
    )
    active_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="新文", content="新正文", book_id=2, sort_num=1)
        )
    )

    assert loaded == [("新正文", "新文")]
    assert adapter.current_text is not None
    assert adapter.current_text.title == "新文"


def test_stale_adjacent_text_success_is_ignored_after_new_text_request():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    adapter._on_text_loaded(
        WenlaiLoadResult(
            text=WenlaiText(title="当前文", content="当前正文", book_id=1, sort_num=1)
        )
    )
    loaded: list[tuple[str, str]] = []
    adapter.textLoaded.connect(lambda text, title: loaded.append((text, title)))

    adapter.loadNextSegment()
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()
    adapter.loadRandomText()
    active_worker = thread_pool.started_workers[1]

    stale_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="下一段", content="下一段正文", book_id=1, sort_num=2)
        )
    )
    active_worker.signals.succeeded.emit(
        WenlaiLoadResult(
            text=WenlaiText(title="新文", content="新正文", book_id=2, sort_num=1)
        )
    )

    assert loaded == [("新正文", "新文")]
    assert adapter.current_text is not None
    assert adapter.current_text.title == "新文"


def test_auth_failure_logs_out_clears_state_and_still_emits_failure():
    adapter, gateway, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    adapter._on_text_loaded(
        WenlaiLoadResult(
            text=WenlaiText(title="当前文", content="当前正文", book_id=1, sort_num=1)
        )
    )
    events: list[str] = []
    adapter.loginStateChanged.connect(lambda: events.append("login"))
    adapter.configChanged.connect(lambda: events.append("config"))
    adapter.loadFailed.connect(lambda message: events.append(f"failed:{message}"))

    adapter.loadRandomText()
    worker = thread_pool.started_workers[0]
    message = "晴发文载文失败：请先在设置页登录晴发文"
    worker.signals.failed.emit(message)

    gateway.logout.assert_called_once_with()
    assert adapter.current_text is None
    assert adapter.is_active is False
    assert events[-1] == f"failed:{message}"
    assert "login" in events[:-1]
    assert "config" in events[:-1]


def test_stale_auth_failure_still_logs_out_and_clears_login_state():
    adapter, gateway, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    adapter._on_text_loaded(
        WenlaiLoadResult(
            text=WenlaiText(title="当前文", content="当前正文", book_id=1, sort_num=1)
        )
    )
    events: list[str] = []
    adapter.loginStateChanged.connect(lambda: events.append("login"))
    adapter.configChanged.connect(lambda: events.append("config"))
    adapter.loadFailed.connect(lambda message: events.append(f"failed:{message}"))

    adapter.loadRandomText()
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()
    stale_worker.signals.failed.emit("晴发文载文失败：登录已过期")

    gateway.logout.assert_called_once_with()
    assert adapter.current_text is None
    assert adapter.is_active is False
    assert "login" in events
    assert "config" in events
    assert not any(event.startswith("failed:") for event in events)


def test_next_segment_requires_current_wenlai_text():
    adapter, _, _ = _build_adapter()
    failures: list[str] = []
    adapter.loadFailed.connect(failures.append)

    adapter.loadNextSegment()

    assert failures == ["请先加载晴发文文本"]


def test_loading_stays_true_until_all_parallel_workers_finish():
    adapter, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.refreshDifficulties()
    adapter.refreshCategories()

    assert adapter.loading is True
    assert len(thread_pool.started_workers) == 2

    thread_pool.started_workers[0].signals.finished.emit()
    assert adapter.loading is True

    thread_pool.started_workers[1].signals.finished.emit()
    assert adapter.loading is False
