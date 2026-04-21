"""基于 ApiClient 的成绩提交实现。"""

from collections.abc import Callable
from typing import Any

from ..infrastructure.api_client import ApiClient
from ..models.entity.session_stat import SessionStat
from ..utils.logger import log_warning


class ApiClientScoreSubmitter:
    """通过 HTTP API 提交成绩到 Spring Boot 后端。

    只有服务端存在的文本才能提交成绩，因此只需传入 text_id。
    """

    def __init__(
        self,
        api_client: ApiClient,
        submit_url: str,
        token_provider: Callable[[], str] = lambda: "",
    ):
        self._api_client = api_client
        self._submit_url = submit_url
        self._token_provider = token_provider

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 及其派生的提交 URL。"""
        new_base_url = new_base_url.rstrip("/")
        self._submit_url = f"{new_base_url}/api/v1/scores"

    def submit(
        self,
        score_data: SessionStat,
        text_id: int,
    ) -> bool:
        """提交成绩到服务器。

        Args:
            score_data: 会话统计数据
            text_id: 服务端文本ID（必须是已存在的文本）

        Returns:
            bool: 提交是否成功
        """
        token = self._token_provider()
        if not token:
            log_warning("[ScoreSubmitter] 无法提交成绩：未登录")
            return False

        payload = self._build_payload(score_data, text_id)
        headers = {"Authorization": f"Bearer {token}"}

        data = self._api_client.request(
            "POST",
            self._submit_url,
            json=payload,
            headers=headers,
        )

        return self._parse_response(data)

    def _build_payload(
        self,
        score_data: SessionStat,
        text_id: int,
    ) -> dict[str, Any]:
        """构建请求体。"""
        return {
            "textId": text_id,
            "speed": round(score_data.speed, 2),
            "effectiveSpeed": round(score_data.effectiveSpeed, 2),
            "keyStroke": round(score_data.keyStroke, 2),
            "codeLength": round(score_data.codeLength, 4),
            "accuracyRate": round(score_data.accuracy, 2),
            "charCount": score_data.char_count,
            "wrongCharCount": score_data.wrong_char_count,
            "duration": round(score_data.time, 2),
        }

    def _parse_response(
        self,
        data: dict[str, Any] | None,
    ) -> bool:
        """解析响应。"""
        if data is None:
            log_warning(
                f"[ScoreSubmitter] 提交失败: {self._api_client.last_error or '网络错误'}"
            )
            return False

        code = data.get("code")
        if code == 200:
            return True

        log_warning(f"[ScoreSubmitter] 提交失败: {data.get('message', '未知错误')}")
        return False


class NoopScoreSubmitter:
    """空实现，用于未登录或禁用提交场景。"""

    def submit(
        self,
        score_data: SessionStat,
        text_id: int,
    ) -> bool:
        return False
