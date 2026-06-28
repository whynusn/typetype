"""AiTextAdapter 测试。"""

from unittest.mock import MagicMock

from src.backend.application.usecases.generate_ai_text_usecase import AiTextResult
from src.backend.presentation.adapters.ai_text_adapter import AiTextAdapter


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker):
        self.started_workers.append(worker)


def _build_adapter() -> tuple[AiTextAdapter, MagicMock, MagicMock, MagicMock]:
    usecase = MagicMock()
    llm = MagicMock()
    config = MagicMock()
    config.ai.api_format = "openai_chat"
    token_store = MagicMock()
    token_store.get_token.return_value = "test-key"
    adapter = AiTextAdapter(
        usecase=usecase,
        llm_provider=llm,
        runtime_config=config,
        token_store=token_store,
    )
    return adapter, usecase, llm, config


def test_request_enqueues_worker():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.requestAiText()

    assert len(thread_pool.started_workers) == 1
    assert adapter.loading is True


def test_worker_calls_task_with_on_chunk_keyword():
    """验证 Worker 用 on_chunk= 关键字调用 task，而非位置参数。"""
    calls: list[dict] = []

    def fake_task(on_chunk=None):
        calls.append({"on_chunk": on_chunk})
        return AiTextResult(success=True, text="ok", title="t")

    usecase = MagicMock()
    usecase.execute.side_effect = fake_task
    llm = MagicMock()
    config = MagicMock()
    config.ai.api_format = "openai_chat"
    token_store = MagicMock()
    token_store.get_token.return_value = "k"
    adapter = AiTextAdapter(
        usecase=usecase,
        llm_provider=llm,
        runtime_config=config,
        token_store=token_store,
    )
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.requestAiText()
    worker = thread_pool.started_workers[0]
    # 手动运行 worker 的 run 方法（不走线程池）
    worker.run()

    assert len(calls) == 1
    assert callable(calls[0]["on_chunk"])


def test_duplicate_request_ignored_while_loading():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.requestAiText()
    adapter.requestAiText()

    assert len(thread_pool.started_workers) == 1


def test_success_emits_text_generated():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    results: list[tuple[str, str]] = []
    adapter.textGenerated.connect(lambda t, title: results.append((t, title)))

    adapter.requestAiText()
    worker = thread_pool.started_workers[0]
    worker.signals.succeeded.emit(
        AiTextResult(success=True, text="你好世界", title="AI 智能推荐")
    )

    assert results == [("你好世界", "AI 智能推荐")]


def test_failure_emits_generation_failed():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    failures: list[str] = []
    adapter.generationFailed.connect(failures.append)

    adapter.requestAiText()
    worker = thread_pool.started_workers[0]
    worker.signals.failed.emit("AI 生成文本失败：timeout")

    assert failures == ["AI 生成文本失败：timeout"]


def test_empty_result_emits_generation_failed():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    failures: list[str] = []
    adapter.generationFailed.connect(failures.append)

    adapter.requestAiText()
    worker = thread_pool.started_workers[0]
    worker.signals.succeeded.emit(
        AiTextResult(success=False, error_message="AI 返回内容为空")
    )

    assert failures == ["AI 返回内容为空"]


def test_loading_clears_when_worker_finishes():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool

    adapter.requestAiText()
    assert adapter.loading is True

    thread_pool.started_workers[0].signals.finished.emit()

    assert adapter.loading is False


def test_loading_state_transitions():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    states: list[bool] = []
    adapter.loadingChanged.connect(lambda: states.append(adapter.loading))

    adapter.requestAiText()
    thread_pool.started_workers[0].signals.finished.emit()

    assert states == [True, False]


def test_streaming_chunks_emit_text_chunk_signal():
    adapter, _, _, _ = _build_adapter()
    thread_pool = DummyThreadPool()
    adapter._thread_pool = thread_pool
    chunks: list[str] = []
    adapter.textChunk.connect(chunks.append)

    adapter.requestAiText()
    worker = thread_pool.started_workers[0]
    worker.signals.chunk.emit("你")
    worker.signals.chunk.emit("好")

    assert chunks == ["你", "好"]


def test_has_api_key_returns_true_when_key_exists():
    adapter, _, _, _ = _build_adapter()

    assert adapter.has_api_key is True


def test_has_api_key_returns_false_when_key_missing():
    adapter, _, _, _ = _build_adapter()
    adapter._token_store.get_token.return_value = ""

    assert adapter.has_api_key is False


def test_update_api_key_saves_to_token_store():
    adapter, _, _, _ = _build_adapter()

    result = adapter.updateApiKey("new-key")

    assert result is True
    adapter._token_store.save_token.assert_called_once_with("ai_api_key", "new-key")


def test_update_base_url_persists_and_syncs_to_provider():
    adapter, _, llm, config = _build_adapter()

    adapter.updateBaseUrl("https://new.api.com/")

    config.update_ai_config.assert_called_once_with(base_url="https://new.api.com/")
    llm.update_config.assert_called_once_with(base_url="https://new.api.com/")


def test_update_model_persists_and_syncs_to_provider():
    adapter, _, llm, config = _build_adapter()

    adapter.updateModel("gpt-4o")

    config.update_ai_config.assert_called_once_with(model="gpt-4o")
    llm.update_config.assert_called_once_with(model="gpt-4o")


def test_update_api_format_persists_and_syncs():
    adapter, _, llm, config = _build_adapter()

    adapter.updateApiFormat("anthropic")

    config.update_ai_config.assert_called_once_with(api_format="anthropic")
    llm.update_config.assert_called_once_with(api_format="anthropic")


def test_update_max_chars_persists_and_syncs():
    adapter, _, llm, config = _build_adapter()

    adapter.updateMaxChars(500)

    config.update_ai_config.assert_called_once_with(max_chars=500)
    llm.update_config.assert_called_once_with(max_chars=500)


def test_api_format_property_reads_from_config():
    adapter, _, _, config = _build_adapter()
    config.ai.api_format = "anthropic"

    assert adapter.api_format == "anthropic"
