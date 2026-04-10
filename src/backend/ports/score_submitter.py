"""成绩提交协议。

定义成绩提交的抽象接口，供集成层实现。
"""

from collections.abc import Callable
from typing import Protocol

from ..models.entity.session_stat import SessionStat


class ScoreSubmitter(Protocol):
    """成绩提交协议。

    实现：
    - ApiClientScoreSubmitter: 通过 HTTP API 提交到 Spring Boot 后端
    - NoopScoreSubmitter: 空实现，用于未登录或禁用提交场景
    """

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
            text_id: 服务器数据库主键 ID，可选
            client_text_id: 客户端生成的 hash ID，可选
            text_content: 文本内容（用于上传），可选
            text_title: 文本标题（用于上传），可选
            on_text_not_found: 文本不存在时的回调(client_text_id, content, title)，可选

        Returns:
            bool: 提交是否成功
        """
        ...
