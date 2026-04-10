"""基于 ApiClient 的成绩提交实现。"""

from collections.abc import Callable
from typing import Any

from ..infrastructure.api_client import ApiClient
from ..models.entity.session_stat import SessionStat
from ..utils.logger import log_warning, log_info


class ApiClientScoreSubmitter:
    """通过 HTTP API 提交成绩到 Spring Boot 后端。"""

    def __init__(
        self,
        api_client: ApiClient,
        submit_url: str,
        token_provider: Callable[[], str] = lambda: "",
    ):
        self._api_client = api_client
        self._submit_url = submit_url
        self._token_provider = token_provider

    def submit(
        self,
        score_data: SessionStat,
        text_id: int | None = None,
        client_text_id: int | None = None,
        text_content: str = "",
        text_title: str = "",
        on_text_not_found: Callable[[int, str, str], None] | None = None,
    ) -> bool:
        """提交成绩到服务器。

        Args:
            score_data: 会话统计数据
            text_id: 服务器数据库主键 ID（可选）
            client_text_id: 客户端生成的 hash ID（可选）
            text_content: 文本内容（用于上传）
            text_title: 文本标题（用于上传）
            on_text_not_found: 文本不存在时的回调

        Returns:
            bool: 提交是否成功
        """
        if text_id is None and client_text_id is None:
            log_warning("[ScoreSubmitter] 无法提交成绩：缺少 text_id 和 client_text_id")
            return False

        token = self._token_provider()
        if not token:
            log_warning("[ScoreSubmitter] 无法提交成绩：未登录")
            return False

        payload = self._build_payload(score_data, text_id, client_text_id)
        headers = {"Authorization": f"Bearer {token}"}

        data = self._api_client.request(
            "POST",
            self._submit_url,
            json=payload,
            headers=headers,
        )

        return self._parse_response(
            data,
            client_text_id or 0,
            text_content,
            text_title,
            on_text_not_found,
        )

    def _build_payload(
        self,
        score_data: SessionStat,
        text_id: int | None,
        client_text_id: int | None,
    ) -> dict[str, Any]:
        """构建请求体。"""
        payload = {
            "speed": round(score_data.speed, 2),
            "effectiveSpeed": round(score_data.effectiveSpeed, 2),
            "keyStroke": round(score_data.keyStroke, 2),
            "codeLength": round(score_data.codeLength, 4),
            "accuracyRate": round(score_data.accuracy, 2),
            "charCount": score_data.char_count,
            "wrongCharCount": score_data.wrong_char_count,
            "duration": round(score_data.time, 2),
        }
        if text_id is not None:
            payload["textId"] = text_id
        if client_text_id is not None:
            payload["clientTextId"] = client_text_id
        return payload

    def _parse_response(
        self,
        data: dict[str, Any] | None,
        client_text_id: int,
        text_content: str,
        text_title: str,
        on_text_not_found: Callable[[int, str, str], None] | None,
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

        if code == 10003 and on_text_not_found and client_text_id:
            log_info(
                f"[ScoreSubmitter] 检测到 NOT_FOUND 调用 callback: client_text_id={client_text_id}"
            )
            on_text_not_found(client_text_id, text_content, text_title)

        log_warning(f"[ScoreSubmitter] 提交失败: {data.get('message', '未知错误')}")
        return False


class NoopScoreSubmitter:
    """空实现，用于未登录或禁用提交场景。"""

    def submit(
        self,
        score_data: SessionStat,
        text_id: int | None = None,
        client_text_id: int | None = None,
        text_content: str = "",
        text_title: str = "",
        on_text_not_found: Callable[[int, str, str], None] | None = None,
    ) -> bool:
        return False
