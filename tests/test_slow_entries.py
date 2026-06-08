"""Tests for CharStatsService.get_slow_entries word-level grouping."""

from src.backend.domain.services.char_stats_service import (
    CharStatsService,
    _is_cjk,
    _cjk_run_segments,
)
from src.backend.integration.noop_char_stats_repository import (
    NoopCharStatsRepository,
)
from src.backend.models.entity.char_stat import CharStat


def test_is_cjk():
    assert _is_cjk("中")
    assert _is_cjk("国")
    assert _is_cjk("装")
    assert not _is_cjk("a")
    assert not _is_cjk("1")
    assert not _is_cjk(",")


def test_cjk_run_segments_consecutive():
    """Consecutive CJK chars should form a single segment."""
    segments = _cjk_run_segments("中国马虎")
    assert len(segments) == 1
    assert segments[0][0] == "中国马虎"


def test_cjk_run_segments_mixed():
    """Mixed CJK and non-CJK chars should split correctly."""
    segments = _cjk_run_segments("中a国,马虎")
    # Expected: ("中", 0, 1), ("a", 1, 2), ("国", 2, 3), (",", 3, 4), ("马虎", 4, 6)
    assert len(segments) == 5
    assert segments[0][0] == "中"
    assert segments[1][0] == "a"
    assert segments[2][0] == "国"
    assert segments[3][0] == ","
    assert segments[4][0] == "马虎"


def test_get_slow_entries_groups_consecutive_slow_chars():
    """Consecutive slow CJK chars in phrase_positions should be grouped."""
    service = CharStatsService(repository=NoopCharStatsRepository())

    slow_a = CharStat(char="马", total_ms=1200, char_count=1)
    slow_b = CharStat(char="虎", total_ms=1000, char_count=1)
    service._cache["马"] = slow_a
    service._cache["虎"] = slow_b
    service._dirty.add("马")
    service._dirty.add("虎")

    text = "中国马虎功夫"
    # 马虎 在位置 2,3，标记为词组
    result = service.get_slow_entries(text, threshold_ms=500, phrase_positions={2, 3})

    assert len(result) >= 1
    word_entries = [entry for entry in result if entry[0] == "马虎"]
    assert len(word_entries) == 1
    assert word_entries[0][1] == 1.2


def test_get_slow_entries_consecutive_but_not_phrase_stays_individual():
    """Consecutive slow chars NOT in phrase_positions should stay individual."""
    service = CharStatsService(repository=NoopCharStatsRepository())

    slow_a = CharStat(char="马", total_ms=1200, char_count=1)
    slow_b = CharStat(char="虎", total_ms=1000, char_count=1)
    service._cache["马"] = slow_a
    service._cache["虎"] = slow_b
    service._dirty.add("马")
    service._dirty.add("虎")

    text = "中国马虎功夫"
    # 没有传 phrase_positions → 逐字输入，不应合并
    result = service.get_slow_entries(text, threshold_ms=500)
    texts = [r[0] for r in result]

    assert "马" in texts
    assert "虎" in texts
    assert "马虎" not in texts


def test_get_slow_entries_non_consecutive_remain_individual():
    """Non-consecutive slow chars should remain as individual entries."""
    service = CharStatsService(repository=NoopCharStatsRepository())

    slow_a = CharStat(char="装", total_ms=800, char_count=1)
    slow_b = CharStat(char="虎", total_ms=600, char_count=1)
    service._cache["装"] = slow_a
    service._cache["虎"] = slow_b
    service._dirty.add("装")
    service._dirty.add("虎")

    # "装" and "虎" are not consecutive in the text
    text = "装备马虎的"
    result = service.get_slow_entries(text, threshold_ms=500)
    texts = [r[0] for r in result]

    assert "装" in texts
    assert "虎" in texts
    assert "装备" not in texts  # 装 is at pos 0, 备 is not slow


def test_get_slow_entries_fallback_same_as_get_slow_chars():
    """Without consecutive slow chars, entries should match get_slow_chars."""
    service = CharStatsService(repository=NoopCharStatsRepository())

    slow_a = CharStat(char="A", total_ms=1000, char_count=1)
    slow_b = CharStat(char="B", total_ms=600, char_count=1)
    service._cache["A"] = slow_a
    service._cache["B"] = slow_b
    service._dirty.add("A")
    service._dirty.add("B")

    text = "X A Y B Z"
    result = service.get_slow_entries(text, threshold_ms=500)
    chars = service.get_slow_chars(threshold_ms=500)

    # Both should have same (char, time) ordering
    assert len(result) == len(chars)
    for (r_char, r_time), (s_char, s_time) in zip(result, chars):
        assert r_char == s_char
        assert r_time == s_time
