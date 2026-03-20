from ..application.ports.char_stats_repository import CharStatsRepository
from ..models.char_stats import CharStat
from .base_worker import BaseWorker


class CharStatFlushWorker(BaseWorker):
    """后台将字符统计数据持久化到数据库，避免阻塞 UI 线程。"""

    def __init__(self, repository: CharStatsRepository, entries: list[CharStat]):
        self._repo = repository
        self._entries = entries
        super().__init__(task=self._flush, error_prefix="持久化字符统计失败")

    def _flush(self) -> None:
        self._repo.save_batch(self._entries)
