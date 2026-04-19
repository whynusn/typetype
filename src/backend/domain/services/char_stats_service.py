from ...models.entity.char_stat import CharStat
from ...ports.async_executor import AsyncExecutor
from ...ports.char_stats_repository import CharStatsRepository


class CharStatsService:
    """字符统计领域服务，纯业务逻辑。

    采用按需加载（lazy loading）：首次遇到字符时才从数据库读取，
    避免启动时全量加载到内存。

    职责：
    - 字符统计数据的缓存管理
    - 击键时间和错误统计的累积
    - 薄弱字符查询逻辑

    不负责：
    - 数据库操作（由 Repository 负责）
    - 异步任务执行（由 AsyncExecutor 负责）
    """

    def __init__(
        self,
        repository: CharStatsRepository,
        async_executor: AsyncExecutor | None = None,
    ):
        self._repo = repository
        self._async_executor = async_executor
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
        self._dirty.clear()

        if self._async_executor:
            self._async_executor.submit(lambda: self._repo.save_batch(entries))
        else:
            self._repo.save_batch(entries)

    def get_weakest_chars(
        self,
        n: int = 10,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
    ) -> list[CharStat]:
        return self._repo.get_chars_by_sort(sort_mode, weights, n)

    def get_all(self) -> dict[str, CharStat]:
        return dict(self._cache)

    def clear(self) -> None:
        self._cache.clear()
        self._dirty.clear()
