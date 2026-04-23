from unittest.mock import MagicMock
from dataclasses import dataclass

from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.application.usecases.load_text_usecase import (
    LoadTextResult,
    LoadTextUseCase,
    TextLoadPlan,
)
from src.backend.ports.local_text_loader import LocalTextLoader
from src.backend.ports.text_provider import TextProvider
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.config.text_source_config import TextSourceEntry
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
    def plan_load(self, source_key: str):
        return DummySourceEntry(key=source_key)

    def load_from_plan(self, source):
        return (True, f"loaded:{source.key}", "")


def test_plan_load_returns_source_entry_from_gateway():
    usecase = LoadTextUseCase(
        text_gateway=DummyTextGateway(),
        clipboard_reader=DummyClipboardReader(),
    )

    plan = usecase.plan_load("remote")
    assert plan.source_entry.key == "remote"


def test_text_source_gateway_plan_load_returns_source_entry():
    local_entry = TextSourceEntry(
        key="local", label="Local", local_path="/tmp/text.txt"
    )
    remote_entry = TextSourceEntry(key="remote", label="Remote")
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
    """本地来源也走 Worker，验证 plan_load 被调用且 runtime_config 不被直接查询。"""
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    source_entry = TextSourceEntry(key="local", label="Local", local_path="local.txt")
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )

    local_text_loader = MagicMock(spec=LocalTextLoader)
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
        local_text_loader=local_text_loader,
    )
    adapter._thread_pool = DummyThreadPool()
    loaded_texts: list[tuple[str, int]] = []
    loading_states: list[bool] = []
    adapter.textLoaded.connect(
        lambda text, text_id, source_label: loaded_texts.append((text, text_id))
    )
    adapter.textLoadingChanged.connect(
        lambda: loading_states.append(adapter.text_loading)
    )

    adapter.requestLoadText("local")

    # 本地来源走 Worker，不再同步调用 load
    assert len(adapter._thread_pool.started_workers) == 1
    worker = adapter._thread_pool.started_workers[0]
    result = LoadTextResult(success=True, text="sync text", text_id=123)
    worker.signals.succeeded.emit(result)
    worker.signals.finished.emit()

    assert loaded_texts == [("sync text", 123)]
    assert loading_states == [True, False]
    assert adapter.text_loading is False
    load_text_usecase.plan_load.assert_called_once_with("local")
    # load is called by the Worker, not by the adapter directly
    load_text_usecase.load.assert_not_called()
    runtime_config.get_text_source.assert_not_called()


def test_text_adapter_enqueues_async_worker_from_application_plan():
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source_options.return_value = []
    runtime_config.default_text_source_key = "builtin_demo"
    source_entry = TextSourceEntry(key="remote", label="Remote", local_path=None)
    load_text_usecase = MagicMock()
    load_text_usecase.plan_load.return_value = TextLoadPlan(
        source_entry=source_entry,
    )

    local_text_loader = MagicMock(spec=LocalTextLoader)
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
        local_text_loader=local_text_loader,
    )
    adapter._thread_pool = DummyThreadPool()
    loaded_texts: list[tuple[str, int]] = []
    adapter.textLoaded.connect(
        lambda text, text_id, source_label: loaded_texts.append((text, text_id))
    )

    adapter.requestLoadText("remote")

    assert len(adapter._thread_pool.started_workers) == 1
    worker = adapter._thread_pool.started_workers[0]
    # Worker now emits LoadTextResult, not just string
    result = LoadTextResult(success=True, text="async text", text_id=456)
    worker.signals.succeeded.emit(result)
    worker.signals.finished.emit()

    assert loaded_texts == [("async text", 456)]
    load_text_usecase.plan_load.assert_called_once_with("remote")
    load_text_usecase.load.assert_not_called()  # worker will call it
    runtime_config.get_text_source.assert_not_called()
