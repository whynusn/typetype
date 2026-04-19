from ..domain.services.char_stats_service import CharStatsService
from .base_worker import BaseWorker


class WeakCharsQueryWorker(BaseWorker):
    """后台从数据库查询薄弱字，避免阻塞 UI 线程。"""

    def __init__(
        self,
        char_stats_service: CharStatsService,
        n: int = 10,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
    ):
        self._char_stats_service = char_stats_service
        self._n = n
        self._sort_mode = sort_mode
        self._weights = weights
        super().__init__(task=self._query, error_prefix="加载薄弱字失败")

    def _query(self) -> list[dict]:
        stats = self._char_stats_service.get_weakest_chars(
            self._n, self._sort_mode, self._weights
        )
        return [s.to_dict() for s in stats]
