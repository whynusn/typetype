from ..application.ports.char_stats_repository import CharStatsRepository
from ..models.char_stats import CharStat
from .base_worker import BaseWorker


class WeakCharsQueryWorker(BaseWorker):
    """后台从数据库查询薄弱字，避免阻塞 UI 线程。"""

    def __init__(self, repository: CharStatsRepository, n: int = 10):
        self._repo = repository
        self._n = n
        super().__init__(task=self._query, error_prefix="加载薄弱字失败")

    def _query(self) -> list[dict]:
        stats: list[CharStat] = self._repo.get_weakest_chars(self._n)
        return [s.to_dict() for s in stats]
