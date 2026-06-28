"""LLM 文本生成适配。

支持三种 API 格式（均支持流式）：
- openai_chat: OpenAI / DeepSeek / 通义千问等 Chat Completions 兼容接口
- openai_response: OpenAI Responses API
- anthropic: Anthropic Messages API
"""

import json as _json
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class AiServiceError(Exception):
    """AI 服务错误。"""


_SYSTEM_PROMPT = (
    "你是打字练习文本生成器。直接输出中文文本，不要任何解释、标题或标记。"
    "严格控制字数，不得超出要求范围。"
)

_USER_PROMPT_TEMPLATE = (
    "用以下汉字写一段中文短文。要求：\n"
    "1. 字数严格控制在{min_chars}到{max_chars}字之间\n"
    "2. 自然流畅，像真实文章片段\n"
    "3. 每个字至少出现一次\n"
    "4. 直接输出正文，不要标题\n\n"
    "汉字：{chars}"
)


class LlmTextProvider:
    """LLM 文本生成适配，支持流式输出。"""

    def __init__(
        self,
        api_client: "ApiClient",
        api_key_provider: Callable[[], str],
        base_url: str,
        model: str,
        api_format: str = "openai_chat",
        max_chars: int = 300,
    ) -> None:
        self._api_client = api_client
        self._api_key_provider = api_key_provider
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_format = api_format
        self._max_chars = max_chars

    @property
    def max_chars(self) -> int:
        return self._max_chars

    def update_config(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_format: str | None = None,
        max_chars: int | None = None,
    ) -> None:
        if base_url is not None:
            self._base_url = base_url.rstrip("/")
        if model is not None:
            self._model = model
        if api_format is not None:
            self._api_format = api_format
        if max_chars is not None:
            self._max_chars = max_chars

    def generate_text_stream(self, weak_chars: list[str]) -> Generator[str, None, None]:
        """流式生成文本，逐块 yield。"""
        api_key = self._api_key_provider()
        if not api_key:
            raise AiServiceError("请先在设置中配置 AI API Key")

        if self._api_format == "anthropic":
            yield from self._stream_anthropic(api_key, weak_chars)
        elif self._api_format == "openai_response":
            yield from self._stream_openai_response(api_key, weak_chars)
        else:
            yield from self._stream_openai_chat(api_key, weak_chars)

    # --- OpenAI Chat Completions 流式 ---

    def _stream_openai_chat(
        self, api_key: str, weak_chars: list[str]
    ) -> Generator[str, None, None]:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": int(self._max_chars * 1.5),
            "stream": True,
        }
        if "deepseek" in self._model.lower():
            body["thinking"] = {"type": "disabled"}

        url = f"{self._base_url}/chat/completions"
        headers = self._auth_headers(api_key)
        for raw in self._api_client.stream(url, json=body, headers=headers):
            try:
                obj = _json.loads(raw)
                delta = obj["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except (_json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    # --- OpenAI Responses API 流式 ---

    def _stream_openai_response(
        self, api_key: str, weak_chars: list[str]
    ) -> Generator[str, None, None]:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "input": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "temperature": 0.8,
            "max_output_tokens": self._max_chars * 2,
            "stream": True,
        }
        url = f"{self._base_url}/responses"
        headers = self._auth_headers(api_key)
        for raw in self._api_client.stream(url, json=body, headers=headers):
            try:
                obj = _json.loads(raw)
                if obj.get("type") == "response.output_text.delta":
                    content = obj.get("delta", "")
                    if content:
                        yield content
            except (_json.JSONDecodeError, KeyError, TypeError):
                continue

    # --- Anthropic Messages API 流式 ---

    def _stream_anthropic(
        self, api_key: str, weak_chars: list[str]
    ) -> Generator[str, None, None]:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": int(self._max_chars * 1.5),
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url = f"{self._base_url}/v1/messages"
        for raw in self._api_client.stream(url, json=body, headers=headers):
            try:
                obj = _json.loads(raw)
                if obj.get("type") == "content_block_delta":
                    delta = obj.get("delta", {})
                    if delta.get("type") == "text_delta":
                        content = delta.get("text", "")
                        if content:
                            yield content
            except (_json.JSONDecodeError, KeyError, TypeError):
                continue

    # --- helpers ---

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def _build_prompt(self, weak_chars: list[str]) -> str:
        chars = "、".join(weak_chars)
        min_chars = max(int(self._max_chars * 0.8), 50)
        return _USER_PROMPT_TEMPLATE.format(
            chars=chars, min_chars=min_chars, max_chars=self._max_chars
        )
