from unittest.mock import MagicMock

from src.backend.application.usecases.load_text_usecase import (
    LoadTextResult,
    TextLoadPlan,
)
from src.backend.config.text_source_config import TextSourceEntry
from src.backend.presentation.adapters.text_adapter import TextAdapter


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter() -> tuple[TextAdapter, MagicMock, MagicMock]:
    runtime_config = MagicMock()
    runtime_config.text_source_config.default_key = "builtin_demo"
    runtime_config.text_source_config.sources = {}
    load_text_usecase = MagicMock()
    local_text_loader = MagicMock()
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
        local_text_loader=local_text_loader,
    )
    return adapter, runtime_config, load_text_usecase


def test_request_load_text_local_source_enqueues_worker():
    """本地来源也走 Worker，避免 _lookup_server_text_id 的同步 HTTP 阻塞 UI。"""
    adapter, runtime_config, load_text_usecase = _build_adapter()
    source_entry = TextSourceEntry(key="local", label="Local", local_path="local.txt")
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded_texts: list[tuple[str, int]] = []
    loading_states: list[bool] = []

    adapter.textLoaded.connect(
        lambda text, text_id, source_label: loaded_texts.append((text, text_id))
    )
    adapter.textLoadingChanged.connect(
        lambda: loading_states.append(adapter.text_loading)
    )

    adapter.requestLoadText("local")

    # 本地来源不再走同步路径，而是走 Worker
    assert len(thread_pool.started_workers) == 1
    worker = thread_pool.started_workers[0]
    result = LoadTextResult(success=True, text="sync text", text_id=123)
    worker.signals.succeeded.emit(result)
    worker.signals.finished.emit()

    assert loaded_texts == [("sync text", 123)]
    assert loading_states == [True, False]
    assert adapter.text_loading is False
    load_text_usecase.plan_load.assert_called_once_with("local")
    load_text_usecase.load.assert_not_called()  # worker will call it
    runtime_config.get_text_source.assert_not_called()


def test_request_load_text_async_enqueues_worker_from_usecase_plan():
    adapter, runtime_config, load_text_usecase = _build_adapter()
    source_entry = TextSourceEntry(key="remote", label="Remote", local_path=None)
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded_texts: list[tuple[str, int]] = []
    loading_states: list[bool] = []

    adapter.textLoaded.connect(
        lambda text, text_id, source_label: loaded_texts.append((text, text_id))
    )
    adapter.textLoadingChanged.connect(
        lambda: loading_states.append(adapter.text_loading)
    )

    adapter.requestLoadText("remote")

    assert len(thread_pool.started_workers) == 1
    worker = thread_pool.started_workers[0]
    result = LoadTextResult(success=True, text="async text", text_id=456)
    worker.signals.succeeded.emit(result)
    worker.signals.finished.emit()

    assert loaded_texts == [("async text", 456)]
    assert loading_states == [True, False]
    assert adapter.text_loading is False
    load_text_usecase.plan_load.assert_called_once_with("remote")
    load_text_usecase.load.assert_not_called()  # worker will call it
    runtime_config.get_text_source.assert_not_called()


def test_request_load_text_reports_planning_errors_without_runtime_config_lookup():
    adapter, runtime_config, load_text_usecase = _build_adapter()
    load_text_usecase.plan_load.side_effect = ValueError("未知文本来源(missing)")
    failures: list[str] = []

    adapter.textLoadFailed.connect(failures.append)

    adapter.requestLoadText("missing")

    assert failures == ["加载文本失败：未知文本来源(missing)"]
    load_text_usecase.load.assert_not_called()
    runtime_config.get_text_source.assert_not_called()


def test_stale_local_text_id_lookup_result_is_not_emitted(monkeypatch):
    adapter, _, load_text_usecase = _build_adapter()
    targets = []

    class FakeThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            targets.append(self._target)

    monkeypatch.setattr("threading.Thread", FakeThread)
    load_text_usecase.lookup_text_id.side_effect = lambda source_key, content: {
        "old text": 111,
        "new text": 222,
    }[content]
    resolved: list[int] = []
    adapter.localTextIdResolved.connect(
        lambda text_id, generation: resolved.append(text_id)
    )

    adapter.lookup_text_id("local", "old text")
    adapter.lookup_text_id("local", "new text")
    # latest-only + single-flight: second request replaces pending payload,
    # so only one worker thread should run and only latest result emitted.
    assert len(targets) == 1
    targets[0]()

    assert resolved == [222]


def test_invalidated_local_text_id_lookup_does_not_call_server(monkeypatch):
    adapter, _, load_text_usecase = _build_adapter()
    targets = []

    class FakeThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            targets.append(self._target)

    monkeypatch.setattr("threading.Thread", FakeThread)

    adapter.lookup_text_id("local", "old text")
    adapter.invalidate_pending_text_id_lookup()
    targets[0]()

    load_text_usecase.lookup_text_id.assert_not_called()


def test_stale_text_load_worker_success_is_ignored_after_clear_active():
    adapter, _, load_text_usecase = _build_adapter()
    source_entry = TextSourceEntry(key="local", label="Local", local_path="local.txt")
    load_text_usecase.plan_load.return_value = TextLoadPlan(source_entry=source_entry)
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded: list[tuple[str, int, str]] = []
    adapter.textLoaded.connect(
        lambda text, text_id, label: loaded.append((text, text_id, label))
    )

    adapter.requestLoadText("local")
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()
    stale_worker.signals.succeeded.emit(
        LoadTextResult(success=True, text="旧文本", text_id=123, source_label="旧")
    )

    assert loaded == []
    assert adapter.text_loading is False


def test_stale_text_load_worker_failure_is_ignored_after_clear_active():
    adapter, _, load_text_usecase = _build_adapter()
    source_entry = TextSourceEntry(key="local", label="Local", local_path="local.txt")
    load_text_usecase.plan_load.return_value = TextLoadPlan(source_entry=source_entry)
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    failures: list[str] = []
    adapter.textLoadFailed.connect(failures.append)

    adapter.requestLoadText("local")
    stale_worker = thread_pool.started_workers[0]
    adapter.clear_active()
    stale_worker.signals.failed.emit("旧请求失败")

    assert failures == []
    assert adapter.text_loading is False


def test_get_source_options_include_local_metadata():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.sources = {
        "builtin_demo": TextSourceEntry(
            key="builtin_demo",
            label="本地示例",
            local_path="resources/texts/builtin_demo.txt",
        ),
        "jisubei": TextSourceEntry(
            key="jisubei",
            label="极速杯",
            has_ranking=True,
        ),
    }

    assert adapter.get_source_options() == [
        {
            "key": "builtin_demo",
            "label": "本地示例",
            "isLocal": True,
            "hasRanking": False,
        },
        {
            "key": "jisubei",
            "label": "极速杯",
            "isLocal": False,
            "hasRanking": True,
        },
    ]


def test_get_local_text_content_reads_from_local_source():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.get_source.return_value = TextSourceEntry(
        key="builtin_demo",
        label="本地示例",
        local_path="resources/texts/builtin_demo.txt",
    )
    adapter._local_text_loader.load_text.return_value = "离线文本"

    assert adapter.get_local_text_content("builtin_demo") == "离线文本"
    runtime_config.text_source_config.get_source.assert_called_once_with("builtin_demo")
    adapter._local_text_loader.load_text.assert_called_once_with(
        "resources/texts/builtin_demo.txt"
    )


def test_get_local_text_content_returns_empty_for_non_local_source():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.get_source.return_value = TextSourceEntry(
        key="jisubei",
        label="极速杯",
    )

    assert adapter.get_local_text_content("jisubei") == ""


def test_lookup_text_id_async_latest_only_emits_latest_result():
    import threading
    from PySide6.QtCore import QCoreApplication

    adapter, _, load_text_usecase = _build_adapter()
    app = QCoreApplication.instance() or QCoreApplication([])
    emitted: list[int] = []
    adapter.localTextIdResolved.connect(
        lambda text_id, generation: emitted.append(text_id)
    )

    gate_first = threading.Event()
    gate_second = threading.Event()

    def lookup_side_effect(source_key: str, content: str):
        if content == "A":
            gate_first.wait(timeout=1)
            return 111
        gate_second.wait(timeout=1)
        return 222

    load_text_usecase.lookup_text_id.side_effect = lookup_side_effect

    adapter.lookup_text_id("k", "A")
    adapter.lookup_text_id("k", "B")

    gate_second.set()
    gate_first.set()

    # 轮询等待后台线程结束
    import time

    deadline = time.time() + 1.0
    while time.time() < deadline and not emitted:
        app.processEvents()
        time.sleep(0.01)

    assert emitted == [222]
