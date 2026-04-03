from unittest.mock import MagicMock

from config.text_source_config import TextSourceEntry
from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.application.usecases.load_text_usecase import (
    LoadTextResult,
    LoadTextUseCase,
    TextLoadPlan,
)
from src.backend.application.ports.local_text_loader import LocalTextLoader
from src.backend.application.ports.text_provider import TextProvider
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.presentation.adapters.text_adapter import TextAdapter


class DummyClipboardReader:
    def __init__(self, text: str = ""):
        self._text = text

    def text(self) -> str:
        return self._text


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


class DummyTextGateway:
    def __init__(self, execution_mode: str = "sync"):
        self.execution_mode = execution_mode

    def get_execution_mode(self, source_key: str) -> str:
        return self.execution_mode

    def load_text_by_key(self, source_key: str):
        return (True, f"loaded:{source_key}", "")


def test_plan_load_returns_application_owned_execution_mode():
    usecase = LoadTextUseCase(
        text_gateway=DummyTextGateway(execution_mode="async"),
        clipboard_reader=DummyClipboardReader(),
    )

    plan = usecase.plan_load("remote")

    assert plan == TextLoadPlan(execution_mode="async")


def test_text_source_gateway_exposes_execution_mode_from_runtime_config():
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source.side_effect = [
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt"),
        TextSourceEntry(key="remote", label="Remote", text_id="remote-id"),
    ]
    gateway = TextSourceGateway(
        runtime_config=runtime_config,
        text_provider=MagicMock(spec=TextProvider),
        local_text_loader=MagicMock(spec=LocalTextLoader),
    )

    assert gateway.get_execution_mode("local") == "sync"
    assert gateway.get_execution_mode("remote") == "async"


def test_text_adapter_uses_usecase_plan_and_skips_runtime_strategy_lookup():
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(execution_mode="sync")
    load_text_usecase.load.return_value = LoadTextResult(success=True, text="sync text")

    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
    )
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


def test_text_adapter_enqueues_async_worker_from_application_plan():
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(execution_mode="async")

    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
    )
    adapter._thread_pool = DummyThreadPool()
    loaded_texts: list[str] = []
    adapter.textLoaded.connect(loaded_texts.append)

    adapter.requestLoadText("remote")

    assert len(adapter._thread_pool.started_workers) == 1
    worker = adapter._thread_pool.started_workers[0]
    worker.signals.succeeded.emit("async text")
    worker.signals.finished.emit()

    assert loaded_texts == ["async text"]
    load_text_usecase.plan_load.assert_called_once_with("remote")
    load_text_usecase.load.assert_not_called()
    runtime_config.get_text_source.assert_not_called()
