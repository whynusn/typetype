"""排行榜加载 Worker - 在后台线程执行网络请求。"""

from typing import Any

from ..integration.leaderboard_fetcher import LeaderboardFetcher
from .base_worker import BaseWorker


class LeaderboardWorker(BaseWorker):
    """排行榜加载 Worker - 在后台线程执行网络请求。"""

    def __init__(
        self,
        leaderboard_fetcher: LeaderboardFetcher,
        source_key: str,
    ):
        self._leaderboard_fetcher = leaderboard_fetcher
        self._source_key = source_key
        super().__init__(task=self._fetch_leaderboard, error_prefix="加载排行榜失败")

    def _fetch_leaderboard(self) -> dict[str, Any]:
        """获取排行榜数据。

        Returns:
            dict 包含:
                - text_info: 文本信息 (id, title)
                - leaderboard: 排行榜记录列表
                - total: 总记录数
        """
        # 1. 获取最新文本
        text_info = self._leaderboard_fetcher.get_latest_text_by_source(
            self._source_key
        )
        if text_info is None:
            raise Exception(f"无法获取 {self._source_key} 的最新文本")

        text_id = text_info.get("id")
        if text_id is None:
            raise Exception("文本信息缺少 ID")

        # 2. 获取排行榜
        leaderboard_data = self._leaderboard_fetcher.get_leaderboard(text_id)
        if leaderboard_data is None:
            raise Exception("无法获取排行榜数据")

        records = leaderboard_data.get("records", [])
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
