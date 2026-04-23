"""文本内容获取 Worker - 按 ID 获取单篇文本的完整内容。"""

from typing import Any

from ..application.gateways.leaderboard_gateway import LeaderboardGateway
from .base_worker import BaseWorker


class TextContentWorker(BaseWorker):
    """按文本 ID 获取完整内容（含 content 字段）。"""

    def __init__(
        self,
        leaderboard_gateway: LeaderboardGateway,
        text_id: int,
    ):
        self._leaderboard_gateway = leaderboard_gateway
        self._text_id = text_id
        super().__init__(task=self._fetch_content, error_prefix="获取文本内容失败")

    def _fetch_content(self) -> dict[str, Any]:
        text = self._leaderboard_gateway.get_text_by_id(self._text_id)
        if text is None:
            raise Exception(f"无法获取文本 ID={self._text_id}")
        return text
