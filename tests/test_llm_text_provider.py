"""LlmTextProvider 流式生成测试。"""

import json
from unittest.mock import MagicMock

import pytest

from src.backend.infrastructure.api_client import AiStreamError
from src.backend.integration.llm_text_provider import AiServiceError, LlmTextProvider


def _build_provider(
    api_format="openai_chat", model="deepseek-chat"
) -> tuple[LlmTextProvider, MagicMock]:
    api_client = MagicMock()
    return LlmTextProvider(
        api_client=api_client,
        api_key_provider=lambda: "test-key",
        base_url="https://api.example.com",
        model=model,
        api_format=api_format,
        max_chars=200,
    ), api_client


def _make_sse_chunks(*json_objects):
    """构造 SSE data 行序列（ApiClient.stream 已剥离 data: 前缀）。"""
    return [json.dumps(obj) for obj in json_objects]


# --- OpenAI Chat Completions 流式 ---


def test_stream_openai_chat_yields_content_deltas():
    provider, api_client = _build_provider("openai_chat")
    api_client.stream.return_value = iter(
        _make_sse_chunks(
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "你"}}]},
            {"choices": [{"delta": {"content": "好"}}]},
            {"choices": [{"delta": {}}]},
        )
    )

    chunks = list(provider.generate_text_stream(["你", "好"]))

    assert chunks == ["你", "好"]
    api_client.stream.assert_called_once()
    url = api_client.stream.call_args.args[0]
    assert url == "https://api.example.com/chat/completions"
    body = api_client.stream.call_args.kwargs["json"]
    assert body["stream"] is True
    assert body["model"] == "deepseek-chat"


def test_stream_openai_chat_disables_thinking_for_deepseek():
    provider, api_client = _build_provider("openai_chat", model="deepseek-chat")
    api_client.stream.return_value = iter(
        _make_sse_chunks(
            {"choices": [{"delta": {"content": "test"}}]},
        )
    )

    list(provider.generate_text_stream(["测"]))

    body = api_client.stream.call_args.kwargs["json"]
    assert body["thinking"] == {"type": "disabled"}


def test_stream_openai_chat_no_thinking_for_non_deepseek():
    provider, api_client = _build_provider("openai_chat", model="gpt-4o-mini")
    api_client.stream.return_value = iter(
        _make_sse_chunks(
            {"choices": [{"delta": {"content": "test"}}]},
        )
    )

    list(provider.generate_text_stream(["测"]))

    body = api_client.stream.call_args.kwargs["json"]
    assert "thinking" not in body


def test_stream_openai_chat_skips_malformed_lines():
    provider, api_client = _build_provider("openai_chat")
    api_client.stream.return_value = iter(
        [
            "{invalid json",
            json.dumps({"choices": [{"delta": {"content": "好"}}]}),
            json.dumps({"unexpected": "structure"}),
        ]
    )

    chunks = list(provider.generate_text_stream(["好"]))

    assert chunks == ["好"]


# --- OpenAI Responses API 流式 ---


def test_stream_openai_response_yields_text_deltas():
    provider, api_client = _build_provider("openai_response")
    api_client.stream.return_value = iter(
        [
            json.dumps({"type": "response.created", "response": {}}),
            json.dumps({"type": "response.output_text.delta", "delta": "你"}),
            json.dumps({"type": "response.output_text.delta", "delta": "好"}),
            json.dumps({"type": "response.output_text.done", "text": "你好"}),
        ]
    )

    chunks = list(provider.generate_text_stream(["你", "好"]))

    assert chunks == ["你", "好"]
    url = api_client.stream.call_args.args[0]
    assert url == "https://api.example.com/responses"


# --- Anthropic Messages API 流式 ---


def test_stream_anthropic_yields_text_deltas():
    provider, api_client = _build_provider("anthropic")
    api_client.stream.return_value = iter(
        [
            json.dumps({"type": "message_start", "message": {}}),
            json.dumps(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }
            ),
            json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "你"},
                }
            ),
            json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "好"},
                }
            ),
            json.dumps({"type": "content_block_stop", "index": 0}),
        ]
    )

    chunks = list(provider.generate_text_stream(["你", "好"]))

    assert chunks == ["你", "好"]
    url = api_client.stream.call_args.args[0]
    assert url == "https://api.example.com/v1/messages"
    headers = api_client.stream.call_args.kwargs["headers"]
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["x-api-key"] == "test-key"


def test_stream_anthropic_skips_non_text_deltas():
    provider, api_client = _build_provider("anthropic")
    api_client.stream.return_value = iter(
        [
            json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "thinking_delta", "text": "thinking..."},
                }
            ),
            json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "你好"},
                }
            ),
        ]
    )

    chunks = list(provider.generate_text_stream(["你", "好"]))

    assert chunks == ["你好"]


# --- 错误处理 ---


def test_stream_raises_when_api_key_is_empty():
    provider, api_client = _build_provider()
    provider._api_key_provider = lambda: ""

    with pytest.raises(AiServiceError, match="API Key"):
        list(provider.generate_text_stream(["测"]))


def test_stream_raises_on_network_error():
    provider, api_client = _build_provider()
    api_client.stream.side_effect = AiStreamError("timeout")

    with pytest.raises(AiStreamError):
        list(provider.generate_text_stream(["测"]))


# --- update_config ---


def test_update_config_changes_base_url():
    provider, _ = _build_provider()

    provider.update_config(base_url="https://new.api.com/")

    assert provider._base_url == "https://new.api.com"


def test_update_config_changes_model():
    provider, _ = _build_provider()

    provider.update_config(model="gpt-4o")

    assert provider._model == "gpt-4o"


def test_update_config_changes_api_format():
    provider, _ = _build_provider("openai_chat")

    provider.update_config(api_format="anthropic")

    assert provider._api_format == "anthropic"
