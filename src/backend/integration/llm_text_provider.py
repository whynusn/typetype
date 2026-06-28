"""LLM 文本生成适配。

支持三种 API 格式：
- openai_chat: OpenAI / DeepSeek / 通义千问等 Chat Completions 兼容接口
- openai_response: OpenAI Responses API
- anthropic: Anthropic Messages API
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class AiServiceError(Exception):
    """AI 服务错误。"""


_SYSTEM_PROMPT = "你是打字练习文本生成器。直接输出中文文本，不要任何解释、标题或标记。"

_USER_PROMPT_TEMPLATE = "用以下汉字写一段{max_chars}字左右的中文短文，要求自然流畅，每个字至少出现一次：\n{chars}"


class LlmTextProvider:
    """LLM 文本生成适配。"""

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

    def generate_text(self, weak_chars: list[str]) -> str:
        """根据薄弱字列表生成练习文本。抛出 AiServiceError。"""
        api_key = self._api_key_provider()
        if not api_key:
            raise AiServiceError("请先在设置中配置 AI API Key")

        if self._api_format == "anthropic":
            return self._call_anthropic(api_key, weak_chars)
        if self._api_format == "openai_response":
            return self._call_openai_response(api_key, weak_chars)
        return self._call_openai_chat(api_key, weak_chars)

    # --- OpenAI Chat Completions ---

    def _call_openai_chat(self, api_key: str, weak_chars: list[str]) -> str:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": self._max_chars * 2,
        }
        # DeepSeek: 禁用思考模式（减少延迟和 token 消耗）
        if "deepseek" in self._model.lower():
            body["thinking"] = {"type": "disabled"}

        response = self._api_client.request(
            "POST",
            f"{self._base_url}/chat/completions",
            json=body,
            headers=self._auth_headers(api_key),
        )
        if response is None:
            raise AiServiceError(f"AI 服务请求失败：{self._api_client.last_error}")
        return self._parse_openai_response(response)

    # --- OpenAI Responses API ---

    def _call_openai_response(self, api_key: str, weak_chars: list[str]) -> str:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "input": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "temperature": 0.8,
            "max_output_tokens": self._max_chars * 2,
        }
        response = self._api_client.request(
            "POST",
            f"{self._base_url}/responses",
            json=body,
            headers=self._auth_headers(api_key),
        )
        if response is None:
            raise AiServiceError(f"AI 服务请求失败：{self._api_client.last_error}")
        return self._parse_openai_response_text(response)

    # --- Anthropic Messages API ---

    def _call_anthropic(self, api_key: str, weak_chars: list[str]) -> str:
        prompt = self._build_prompt(weak_chars)
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_chars * 2,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        response = self._api_client.request(
            "POST",
            f"{self._base_url}/v1/messages",
            json=body,
            headers=headers,
        )
        if response is None:
            raise AiServiceError(f"AI 服务请求失败：{self._api_client.last_error}")
        return self._parse_anthropic_response(response)

    # --- helpers ---

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def _build_prompt(self, weak_chars: list[str]) -> str:
        chars = "、".join(weak_chars)
        return _USER_PROMPT_TEMPLATE.format(chars=chars, max_chars=self._max_chars)

    @staticmethod
    def _parse_openai_response(response: dict[str, Any]) -> str:
        try:
            msg = response["choices"][0]["message"]
            # DeepSeek thinking 模式下 content 可能为空，尝试 reasoning_content
            content = (msg.get("content") or "").strip()
            if not content:
                content = (msg.get("reasoning_content") or "").strip()
        except (KeyError, IndexError, TypeError) as e:
            raise AiServiceError(f"AI 响应格式异常：{e}")
        if not content:
            raise AiServiceError("AI 返回内容为空")
        return content

    @staticmethod
    def _parse_openai_response_text(response: dict[str, Any]) -> str:
        """解析 OpenAI Responses API 格式。"""
        try:
            # output 是一个数组，取第一个 text 类型的项
            for item in response.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") == "output_text":
                            text = block.get("text", "").strip()
                            if text:
                                return text
            # 回退：尝试顶层 text 字段
            text = response.get("text", "").strip()
            if text:
                return text
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise AiServiceError(f"AI 响应格式异常：{e}")
        raise AiServiceError("AI 返回内容为空")

    @staticmethod
    def _parse_anthropic_response(response: dict[str, Any]) -> str:
        try:
            content_blocks = response.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        return text
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise AiServiceError(f"AI 响应格式异常：{e}")
        raise AiServiceError("AI 返回内容为空")
