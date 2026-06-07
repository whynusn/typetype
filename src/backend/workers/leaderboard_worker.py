"""排行榜加载 Worker - 在后台线程执行网络请求。"""

from typing import Any

from ..application.gateways.leaderboard_gateway import LeaderboardGateway
from .base_worker import BaseWorker


class LeaderboardWorker(BaseWorker):
    """排行榜加载 Worker - 在后台线程执行网络请求。

    支持两种模式：
    - source_key 模式：先获取最新文本，再获取排行榜
    - text_id 模式：直接通过 text_id 获取排行榜和文本信息
    """

    def __init__(
        self,
        leaderboard_gateway: LeaderboardGateway,
        source_key: str | None = None,
        text_id: int | None = None,
    ):
        self._leaderboard_gateway = leaderboard_gateway
        self._source_key = source_key
        self._text_id = text_id
        super().__init__(task=self._fetch_leaderboard, error_prefix="加载排行榜失败")

    def _fetch_leaderboard(self) -> dict[str, Any]:
        """获取排行榜数据。"""
        if self._text_id is not None:
            return self._fetch_by_text_id(self._text_id)
        return self._fetch_by_source_key(self._source_key)

    def _fetch_by_source_key(self, source_key: str | None) -> dict[str, Any]:
        """通过 source_key 获取排行榜（先获取最新文本）。"""
        if source_key is None:
            raise Exception("source_key 和 text_id 不能同时为空")

        # 1. 获取最新文本
        text_info = self._leaderboard_gateway.get_latest_text_by_source(source_key)
        if text_info is None:
            raise Exception(f"无法获取 {source_key} 的最新文本")

        text_id = text_info.get("id")
        if text_id is None:
            raise Exception("文本信息缺少 ID")

        # 2. 获取排行榜
        leaderboard_data = self._leaderboard_gateway.get_leaderboard(text_id)
        if leaderboard_data is None:
            raise Exception("无法获取排行榜数据")

        records = leaderboard_data.get("leaderboard", [])
        total = leaderboard_data.get("total", 0)

        return {
            "text_info": {
                "id": text_id,
                "title": text_info.get("title", ""),
                "content": text_info.get("content", ""),
            },
            "leaderboard": records,
            "total": total,
        }

    def _fetch_by_text_id(self, text_id: int) -> dict[str, Any]:
        """直接通过 text_id 获取排行榜。

        注意：text_info 中不返回 title/content——title 由前端文本列表
        的 delegate onClicked 设置 selectedTextTitle，无需额外网络请求。
        """
        # 获取排行榜（只取排行榜数据，跳过 get_text_by_id 的冗余网络请求）
        leaderboard_data = self._leaderboard_gateway.get_leaderboard(text_id)
        if leaderboard_data is None:
            raise Exception("无法获取排行榜数据")

        records = leaderboard_data.get("leaderboard", [])
        total = leaderboard_data.get("total", 0)

        return {
            "text_info": {
                "id": text_id,
            },
            "leaderboard": records,
            "total": total,
        }
