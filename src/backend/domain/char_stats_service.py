from PySide6.QtCore import QThreadPool

from ..application.ports.char_stats_repository import CharStatsRepository
from ..models.char_stats import CharStat
from ..workers.char_stat_flush_worker import CharStatFlushWorker


class CharStatsService:
    """字符统计领域服务。

    按需加载（lazy loading）：首次遇到字符时才从数据库读取，
    避免启动时全量加载到内存。
    """

    def __init__(self, repository: CharStatsRepository):
        self._repo = repository
        self._cache: dict[str, CharStat] = {}
        self._dirty: set[str] = set()
        self._repo.init_db()

    def accumulate(self, char: str, keystroke_ms: float, is_error: bool) -> None:
        if char not in self._cache:
            existing = self._repo.get(char)
            self._cache[char] = existing if existing else CharStat(char)
        self._cache[char].accumulate(keystroke_ms, is_error)
        self._dirty.add(char)

    def warm_chars(self, chars: list[str]) -> None:
        if not chars:
            return
        existing = self._repo.get_batch(chars)
        for stat in existing:
            self._cache[stat.char] = stat
        for char in chars:
            if char not in self._cache:
                self._cache[char] = CharStat(char)

    def flush(self) -> None:
        if not self._dirty:
            return
        entries = [self._cache[c] for c in self._dirty if c in self._cache]
        self._repo.save_batch(entries)
        self._dirty.clear()

    def flush_async(self) -> None:
        if not self._dirty:
            return
        entries = [self._cache[c] for c in self._dirty if c in self._cache]
        worker = CharStatFlushWorker(repository=self._repo, entries=entries)
        QThreadPool.globalInstance().start(worker)
        self._dirty.clear()

    def get_weakest_chars(self, n: int = 10) -> list[CharStat]:
        return self._repo.get_weakest_chars(n)

    def get_all(self) -> dict[str, CharStat]:
        return dict(self._cache)

    def clear(self) -> None:
        self._cache.clear()
        self._dirty.clear()
