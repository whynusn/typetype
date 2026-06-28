"""LLM 文本生成适配（OpenAI 兼容 Chat Completions API）。

支持 OpenAI / DeepSeek / 通义千问等兼容接口。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class AiServiceError(Exception):
    """AI 服务错误。"""


_SYSTEM_PROMPT = (
    "你是一个中文打字练习文本生成器。生成自然流畅的中文文段，适合打字练习。"
)

_USER_PROMPT_TEMPLATE = (
    "根据以下薄弱字生成一段约{max_chars}字的中文练习文本。\n\n"
    "薄弱字（按错误率从高到低）：{chars}\n\n"
    "要求：\n"
    "1. 文本自然流畅，像真实文章片段\n"
    "2. 尽量多覆盖薄弱字，每个至少出现1次\n"
    "3. 薄弱字嵌入自然语境，不要堆砌\n"
    "4. 直接输出文本内容，不要解释\n"
    "5. 约{max_chars}字"
)


class LlmTextProvider:
    """LLM 文本生成适配。"""

    def __init__(
        self,
        api_client: "ApiClient",
        api_key_provider: Callable[[], str],
        base_url: str,
        model: str,
        max_chars: int = 300,
    ) -> None:
        self._api_client = api_client
        self._api_key_provider = api_key_provider
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_chars = max_chars

    def generate_text(self, weak_chars: list[str]) -> str:
        """根据薄弱字列表生成练习文本。抛出 AiServiceError。"""
        api_key = self._api_key_provider()
        if not api_key:
            raise AiServiceError("请先在设置中配置 AI API Key")

        prompt = self._build_prompt(weak_chars)
        response = self._api_client.request(
            "POST",
            f"{self._base_url}/chat/completions",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
                "max_tokens": self._max_chars * 2,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response is None:
            error = self._api_client.last_error
            raise AiServiceError(f"AI 服务请求失败：{error}")
        return self._parse_response(response)

    def _build_prompt(self, weak_chars: list[str]) -> str:
        chars = "、".join(weak_chars)
        return _USER_PROMPT_TEMPLATE.format(chars=chars, max_chars=self._max_chars)

    @staticmethod
    def _parse_response(response: dict[str, Any]) -> str:
        try:
            content = response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise AiServiceError(f"AI 响应格式异常：{e}")
        if not content:
            raise AiServiceError("AI 返回内容为空")
        return content
