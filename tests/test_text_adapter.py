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
    runtime_config.text_source_config.get_source_options.return_value = []
    runtime_config.text_source_config.default_key = "builtin_demo"
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
        lambda text, text_id: loaded_texts.append((text, text_id))
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
        lambda text, text_id: loaded_texts.append((text, text_id))
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
