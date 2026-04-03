from unittest.mock import MagicMock

from src.backend.application.usecases.load_text_usecase import (
    LoadTextResult,
    TextLoadPlan,
)
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.presentation.adapters.text_adapter import TextAdapter


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter() -> tuple[TextAdapter, MagicMock, MagicMock]:
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    load_text_usecase = MagicMock()
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
    )
    return adapter, runtime_config, load_text_usecase


def test_request_load_text_sync_uses_usecase_plan_only():
    adapter, runtime_config, load_text_usecase = _build_adapter()
    load_text_usecase.plan_load.return_value = TextLoadPlan(execution_mode="sync")
    load_text_usecase.load.return_value = LoadTextResult(success=True, text="sync text")
    loaded_texts: list[str] = []
    loading_states: list[bool] = []

    adapter.textLoaded.connect(loaded_texts.append)
    adapter.textLoadingChanged.connect(
        lambda: loading_states.append(adapter.text_loading)
    )

    adapter.requestLoadText("local")

    assert loaded_texts == ["sync text"]
    assert loading_states == [True, False]
    assert adapter.text_loading is False
    load_text_usecase.plan_load.assert_called_once_with("local")
    load_text_usecase.load.assert_called_once_with("local")
    runtime_config.get_text_source.assert_not_called()


def test_request_load_text_async_enqueues_worker_from_usecase_plan():
    adapter, runtime_config, load_text_usecase = _build_adapter()
    load_text_usecase.plan_load.return_value = TextLoadPlan(execution_mode="async")
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    loaded_texts: list[str] = []
    loading_states: list[bool] = []

    adapter.textLoaded.connect(loaded_texts.append)
    adapter.textLoadingChanged.connect(
        lambda: loading_states.append(adapter.text_loading)
    )

    adapter.requestLoadText("remote")

    assert len(thread_pool.started_workers) == 1
    worker = thread_pool.started_workers[0]
    worker.signals.succeeded.emit("async text")
    worker.signals.finished.emit()

    assert loaded_texts == ["async text"]
    assert loading_states == [True, False]
    assert adapter.text_loading is False
    load_text_usecase.plan_load.assert_called_once_with("remote")
    load_text_usecase.load.assert_not_called()
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
