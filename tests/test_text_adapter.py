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


class CapturingExecutor:
    """Captures submitted callables without executing them.

    Replaces the old FakeThread mock pattern that monkeypatched
    threading.Thread - with ThreadPoolExecutor, thread creation is
    internal, so we inject a fake executor instead.
    """

    def __init__(self):
        self.submitted: list[callable] = []

    def submit(self, fn, /, *args, **kwargs):
        self.submitted.append(fn)

    def shutdown(self, wait=True):
        pass


def _build_adapter() -> tuple[TextAdapter, MagicMock, MagicMock]:
    runtime_config = MagicMock()
    runtime_config.text_source_config.default_key = "builtin_demo"
    runtime_config.text_source_config.sources = {}
    runtime_config.text_source_config.get_source.side_effect = lambda key: (
        runtime_config.text_source_config.sources.get(key)
    )
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
        "local_b": TextSourceEntry(
            key="local_b",
            label="本地B",
            local_path="resources/texts/local_b.txt",
        ),
    }

    assert adapter.get_source_options() == [
        {
            "key": "builtin_demo",
            "label": "本地示例",
            "isLocal": True,
        },
        {
            "key": "local_b",
            "label": "本地B",
            "isLocal": True,
        },
    ]


def test_startup_source_uses_default_when_default_is_local():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.default_key = "builtin_demo"
    runtime_config.text_source_config.sources = {
        "builtin_demo": TextSourceEntry(
            key="builtin_demo",
            label="本地示例",
            local_path="resources/texts/builtin_demo.txt",
        ),
        "old": TextSourceEntry(key="old", label="Old"),
    }

    assert adapter.get_startup_source_key() == "builtin_demo"


def test_startup_source_prefers_local_sources():
    """v2 收敛后所有来源均为本地（is_local 恒 True），默认 key 优先。"""
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.default_key = "old"
    runtime_config.text_source_config.sources = {
        "old": TextSourceEntry(key="old", label="Old"),
        "builtin_demo": TextSourceEntry(
            key="builtin_demo",
            label="本地示例",
            local_path="resources/texts/builtin_demo.txt",
        ),
    }

    assert adapter.get_startup_source_key() == "old"


def test_startup_source_keeps_default_when_no_local_source_exists():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.default_key = "old"
    runtime_config.text_source_config.sources = {
        "old": TextSourceEntry(key="old", label="Old"),
    }

    assert adapter.get_startup_source_key() == "old"


def test_get_local_text_content_reads_from_local_source():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.sources = {
        "builtin_demo": TextSourceEntry(
            key="builtin_demo",
            label="本地示例",
            local_path="resources/texts/builtin_demo.txt",
        )
    }
    adapter._local_text_loader.load_text.return_value = "离线文本"

    assert adapter.get_local_text_content("builtin_demo") == "离线文本"
    runtime_config.text_source_config.get_source.assert_called_once_with("builtin_demo")
    adapter._local_text_loader.load_text.assert_called_once_with(
        "resources/texts/builtin_demo.txt"
    )


def test_get_local_text_content_returns_empty_for_non_local_source():
    adapter, runtime_config, _ = _build_adapter()
    runtime_config.text_source_config.sources = {
        "jisubei": TextSourceEntry(
            key="jisubei",
            label="极速杯",
        )
    }

    assert adapter.get_local_text_content("jisubei") == ""


def test_start_file_text_session_uses_injected_provider_cls(tmp_path):
    from src.backend.config.runtime_config import RuntimeConfig
    from src.backend.integration.file_segment_provider import FileSegmentProvider
    from src.backend.models.dto.text_session import TextKind

    runtime_config = RuntimeConfig()
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=MagicMock(),
        local_text_loader=MagicMock(),
        file_segment_provider_cls=FileSegmentProvider,
    )
    p = tmp_path / "sample.txt"
    p.write_text("你好世界", encoding="utf-8")

    result = adapter.startFileTextSession(
        file_path=str(p),
        kind=TextKind.LOCAL_ARTICLE,
        identifier="a1",
        title="示例",
        version="v1",
        slice_size=2,
    )

    assert result is not None
    assert result.content == "你好"
    assert adapter.text_session_usecase is not None


def test_start_file_text_session_falls_back_to_default_provider(tmp_path):
    """未注入 file_segment_provider_cls 时懒加载默认实现兜底（兼容直接构造）。"""
    from src.backend.config.runtime_config import RuntimeConfig
    from src.backend.models.dto.text_session import TextKind

    runtime_config = RuntimeConfig()
    adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=MagicMock(),
        local_text_loader=MagicMock(),
    )
    p = tmp_path / "sample.txt"
    p.write_text("你好世界", encoding="utf-8")

    result = adapter.startFileTextSession(
        file_path=str(p),
        kind=TextKind.LOCAL_ARTICLE,
        identifier="a1",
        title="示例",
        version="v1",
        slice_size=2,
    )

    assert result is not None
    assert result.content == "你好"


def test_runtime_config_public_accessor():
    adapter, runtime_config, _ = _build_adapter()

    assert adapter.runtime_config is runtime_config
