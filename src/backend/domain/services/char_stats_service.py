import heapq

from ...models.entity.char_stat import CharStat
from ...ports.async_executor import AsyncExecutor
from ...ports.char_stats_repository import CharStatsRepository
from ...utils.logger import log_debug


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
        self._cache: dict[str, CharStat] = {}   # 全局数据（持久化，弱字分析用）
        self._dirty: set[str] = set()            # 全局脏标记
        self._session_cache: dict[str, CharStat] = {}  # 会话数据（慢字统计用）
        self._session_dirty: set[str] = set()
        self._repo.init_db()

    def accumulate(self, char: str, keystroke_ms: float, is_error: bool) -> None:
        # 全局缓存（持久化，弱字分析）
        if char not in self._cache:
            existing = self._repo.get(char)
            self._cache[char] = existing if existing else CharStat(char)
        self._cache[char].accumulate(keystroke_ms, is_error)
        self._dirty.add(char)

        # 会话缓存（慢字统计，从零开始）
        if char not in self._session_cache:
            self._session_cache[char] = CharStat(char)
        session_stat = self._session_cache[char]
        old_avg = session_stat.avg_ms
        old_count = session_stat.char_count
        session_stat.accumulate(keystroke_ms, is_error)
        self._session_dirty.add(char)
        log_debug(
            f"[CharStatsService] accumulate: char='{char}' "
            f"input_ms={keystroke_ms:.0f} session_count={old_count} session_avg={old_avg:.0f}ms "
            f"→ session_count={session_stat.char_count} session_avg={session_stat.avg_ms:.0f}ms"
        )

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
        heap: list[tuple[float, str]] = []
        for char in self._session_dirty:
            if char in self._session_cache:
                stat = self._session_cache[char]
                if stat.avg_ms >= threshold_ms:
                    time_s = round(stat.avg_ms / 1000, 1)
                    if len(heap) < limit:
                        heapq.heappush(heap, (time_s, char))
                    elif time_s > heap[0][0]:
                        heapq.heapreplace(heap, (time_s, char))
        return [(char, time) for time, char in sorted(heap, reverse=True)]

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
        for char in self._session_dirty:
            if char in self._session_cache:
                stat = self._session_cache[char]
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

        log_debug(
            f"[CharStatsService] get_slow_entries: text='{text}' "
            f"slow_positions={sorted(slow_positions)} phrase_positions={sorted(phrase)}"
        )

        # 1. 提取 phrase_positions 中的连续区间（词组区间）
        phrase_ranges: list[tuple[int, int]] = []
        if phrase:
            sorted_phrase = sorted(phrase)
            start = sorted_phrase[0]
            prev = start
            for pos in sorted_phrase[1:]:
                if pos == prev + 1:
                    prev = pos
                else:
                    phrase_ranges.append((start, prev + 1))
                    start = pos
                    prev = pos
            phrase_ranges.append((start, prev + 1))

        log_debug(f"[CharStatsService] phrase_ranges={phrase_ranges}")

        # 2. 先处理词组区间：只要区间内包含慢字，就把整个词组作为一个条目
        #    时间取词组内所有字的耗时之和（反映词组整体输入耗时）
        covered_slow: set[int] = set()
        result: list[tuple[str, float]] = []
        for start, end in phrase_ranges:
            range_slow = [p for p in range(start, end) if p in slow_positions]
            if range_slow:
                word_text = "".join(text[p] for p in range(start, end))
                # 词组耗时 = 词组内所有字的时间之和（每个字的 per_char_ms 相同）
                sum_time = round(sum(slow_data[text[p]] for p in range_slow), 1)
                result.append((word_text, sum_time))
                covered_slow.update(range_slow)
                log_debug(
                    f"[CharStatsService] phrase word: '{word_text}' "
                    f"range=({start},{end}) slow_in_range={range_slow} sum_time={sum_time}s"
                )

        # 3. 处理未被词组覆盖的慢字（逐字输入部分），不合并
        remaining_slow = sorted(slow_positions - covered_slow)
        for pos in remaining_slow:
            ch = text[pos]
            if ch in slow_data:
                result.append((ch, slow_data[ch]))
                log_debug(
                    f"[CharStatsService] remaining single: '{ch}' time={slow_data[ch]}s"
                )

        heap: list[tuple[float, str]] = []
        for entry_text, time_s in result:
            if len(heap) < limit:
                heapq.heappush(heap, (time_s, entry_text))
            elif time_s > heap[0][0]:
                heapq.heapreplace(heap, (time_s, entry_text))
        top = [(entry_text, time) for time, entry_text in sorted(heap, reverse=True)]
        log_debug(f"[CharStatsService] get_slow_entries result: {top}")
        return top

    def clear(self) -> None:
        """清空会话级数据（慢字统计），保留全局数据（弱字分析）。"""
        self._session_cache.clear()
        self._session_dirty.clear()
