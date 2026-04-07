from unittest.mock import MagicMock
from dataclasses import dataclass

from config.text_source_config import TextSourceEntry
from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.application.usecases.load_text_usecase import (
    LoadTextResult,
    LoadTextUseCase,
    TextLoadPlan,
)
from src.backend.ports.local_text_loader import LocalTextLoader
from src.backend.ports.text_provider import TextProvider
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


@dataclass
class DummySourceEntry:
    key: str
    local_path: str | None = None


class DummyTextGateway:
    def __init__(self, execution_mode: str = "sync"):
        self.execution_mode = execution_mode

    def plan_load(self, source_key: str):
        dummy_entry = DummySourceEntry(key=source_key)
        if self.execution_mode == "sync":
            dummy_entry.local_path = f"{source_key}.txt"
        return dummy_entry

    def load_from_plan(self, source):
        return (True, f"loaded:{source.key}", "")


def test_plan_load_returns_application_owned_execution_mode():
    usecase = LoadTextUseCase(
        text_gateway=DummyTextGateway(execution_mode="async"),
        clipboard_reader=DummyClipboardReader(),
    )

    plan = usecase.plan_load("remote")

    assert plan.execution_mode == "async"
    assert plan.source_entry.key == "remote"


def test_text_source_gateway_exposes_execution_mode_from_runtime_config():
    local_entry = TextSourceEntry(
        key="local", label="Local", local_path="/tmp/text.txt"
    )
    remote_entry = TextSourceEntry(key="remote", label="Remote", text_id="remote-id")
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source.side_effect = [local_entry, remote_entry]
    gateway = TextSourceGateway(
        runtime_config=runtime_config,
        text_provider=MagicMock(spec=TextProvider),
        local_text_loader=MagicMock(spec=LocalTextLoader),
    )

    entry1 = gateway.plan_load("local")
    assert entry1 is local_entry

    entry2 = gateway.plan_load("remote")
    assert entry2 is remote_entry


def test_text_adapter_uses_usecase_plan_and_skips_runtime_strategy_lookup():
    from config.text_source_config import TextSourceEntry

    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    source_entry = TextSourceEntry(key="local", label="Local", local_path="local.txt")
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )
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
    # load receives the plan object, not source_key
    assert load_text_usecase.load.called
    args = load_text_usecase.load.call_args
    assert args[0][0] == load_text_usecase.plan_load.return_value
    runtime_config.get_text_source.assert_not_called()


def test_text_adapter_enqueues_async_worker_from_application_plan():
    from config.text_source_config import TextSourceEntry

    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    source_entry = TextSourceEntry(key="remote", label="Remote", local_path=None)
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )

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
    load_text_usecase.load.assert_not_called()  # worker will call it
    runtime_config.get_text_source.assert_not_called()
