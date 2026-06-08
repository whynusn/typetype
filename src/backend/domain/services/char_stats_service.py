from ...models.entity.char_stat import CharStat
from ...ports.async_executor import AsyncExecutor
from ...ports.char_stats_repository import CharStatsRepository


def _is_cjk(char: str) -> bool:
    """Check if a character is a CJK Unified Ideograph."""
    cp = ord(char)
    return 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF


def _cjk_run_segments(text: str) -> list[tuple[str, int, int]]:
    """Split text into segments where consecutive CJK chars form a segment.

    Each segment is (text, start_pos, end_pos). Multi-char segments consist
    of consecutive CJK chars; single-char segments are non-CJK characters.
    """
    segments: list[tuple[str, int, int]] = []
    i = 0
    while i < len(text):
        if _is_cjk(text[i]):
            start = i
            while i < len(text) and _is_cjk(text[i]):
                i += 1
            segments.append((text[start:i], start, i))
        else:
            segments.append((text[i], i, i + 1))
            i += 1
    return segments


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

    def get_slow_chars(
        self, threshold_ms: float = 500.0, limit: int = 10
    ) -> list[tuple[str, float]]:
        chars_with_times = []
        for char in self._dirty:
            if char in self._cache:
                stat = self._cache[char]
                if stat.avg_ms >= threshold_ms:
                    chars_with_times.append((char, round(stat.avg_ms / 1000, 1)))
        chars_with_times.sort(key=lambda x: x[1], reverse=True)
        return chars_with_times[:limit]

    def get_slow_entries(
        self,
        text: str,
        threshold_ms: float = 500.0,
        limit: int = 10,
        phrase_positions: set[int] | None = None,
    ) -> list[tuple[str, float]]:
        """Get slow entries, grouping only chars actually typed as a phrase.

        Args:
            text: The source text being typed (for word boundary detection).
            threshold_ms: Minimum average time in ms to be considered slow.
            limit: Maximum number of entries to return.
            phrase_positions: Positions marked as phrase input (grow_length > 1).
                Only consecutive positions BOTH slow AND in phrase_positions are grouped.

        Returns:
            List of (entry_text, avg_time_seconds) sorted by time descending.
        """
        slow_data: dict[str, float] = {}
        for char in self._dirty:
            if char in self._cache:
                stat = self._cache[char]
                if stat.avg_ms >= threshold_ms:
                    slow_data[char] = round(stat.avg_ms / 1000, 1)

        if not slow_data:
            return []

        slow_positions: set[int] = set()
        for i, ch in enumerate(text):
            if ch in slow_data:
                slow_positions.add(i)

        if not slow_positions:
            return list(slow_data.items())

        phrase = phrase_positions or set()

        # Group consecutive slow positions, but only if ALL are in phrase_positions
        sorted_pos = sorted(slow_positions)
        groups: list[list[int]] = [[sorted_pos[0]]]
        for pos in sorted_pos[1:]:
            prev = groups[-1][-1]
            # 只有当两个位置都标记为词组且相邻时才合并
            if pos == prev + 1 and prev in phrase and pos in phrase:
                groups[-1].append(pos)
            else:
                groups.append([pos])

        result: list[tuple[str, float]] = []
        for group in groups:
            if len(group) >= 2:
                word_text = "".join(text[p] for p in group)
                max_time = max(slow_data[text[p]] for p in group)
                result.append((word_text, max_time))
            else:
                ch = text[group[0]]
                if ch in slow_data:
                    result.append((ch, slow_data[ch]))

        result.sort(key=lambda x: x[1], reverse=True)
        return result[:limit]

    def clear(self) -> None:
        self._cache.clear()
        self._dirty.clear()
