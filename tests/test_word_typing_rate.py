"""打词率（word typing rate）计算测试。"""

from src.backend.domain.services.typing_service import TypingService

import pytest


class TestComputeWordTypingRate:
    """测试打词率计算逻辑"""

    def test_empty_document_returns_zero(self):
        """空文档打词率为 0"""
        service = TypingService()
        service.set_plain_doc("")
        service.set_total_chars(0)
        assert service._compute_word_typing_rate() == 0.0

    def test_no_cjk_chars_returns_zero(self):
        """无 CJK 字符的打词率为 0"""
        service = TypingService()
        service.set_plain_doc("hello 123 !!!")
        service.set_total_chars(13)
        # All chars typed
        for i in range(13):
            service._state.char_commit_times[i] = 100.0 + i
        assert service._compute_word_typing_rate() == 0.0

    def test_no_timings_returns_zero(self):
        """无时间记录的打词率为 0"""
        service = TypingService()
        service.set_plain_doc("中国")
        service.set_total_chars(2)
        assert service._compute_word_typing_rate() == 0.0

    def test_single_cjk_chars_no_words(self):
        """单个 CJK 字符（无连续 ≥2 的片段）打词率为 0"""
        service = TypingService()
        service.set_plain_doc("一国 二")
        service.set_total_chars(4)
        # All chars typed, but isolated (non-consecutive in source)
        service._state.char_commit_times[0] = 100.0  # 一
        service._state.char_commit_times[2] = 201.0  # 二 (gap > 300ms from pos 0)
        service._state.char_commit_times[3] = 202.0  # 二 has no CJK neighbor within gap
        assert service._compute_word_typing_rate() == 0.0

    def test_two_consecutive_cjk_within_gap_is_word(self):
        """连续 2 个 CJK 字符间隔 ≤300ms 算词组"""
        service = TypingService()
        service.set_plain_doc("中国")
        service.set_total_chars(2)
        service._state.char_commit_times[0] = 100.0  # 中
        service._state.char_commit_times[1] = 120.0  # 国 (gap=20ms, within 300ms)
        rate = service._compute_word_typing_rate()
        assert rate == 100.0  # Both chars in word = 2/2 = 100%

    def test_two_consecutive_cjk_large_gap_not_word(self):
        """连续 2 个 CJK 字符间隔 >300ms 不算词组"""
        service = TypingService()
        service.set_plain_doc("中国")
        service.set_total_chars(2)
        service._state.char_commit_times[0] = 100.0
        service._state.char_commit_times[1] = 500.0  # gap=400ms > 300ms
        rate = service._compute_word_typing_rate()
        assert rate == 0.0

    def test_four_char_word(self):
        """连续 4 个 CJK 字符全部 ≤300ms 算完整词组"""
        service = TypingService()
        service.set_plain_doc("中华人民共和国")
        service.set_total_chars(7)
        # Only first 4 are in a word group
        service._state.char_commit_times[0] = 100.0
        service._state.char_commit_times[1] = 150.0  # gap=50ms
        service._state.char_commit_times[2] = 200.0  # gap=50ms
        service._state.char_commit_times[3] = 250.0  # gap=50ms
        # pos 4-6 not timed yet (not typed)
        rate = service._compute_word_typing_rate()
        assert rate == 100.0  # 4/4 = 100%

    def test_partial_word_rate(self):
        """混合输入：部分在词组中、部分不在"""
        service = TypingService()
        service.set_plain_doc("中国功夫马虎")
        service.set_total_chars(6)
        # "中国" is a word (gap=50ms)
        # "功夫" is a word (gap=50ms)
        # "马虎" — gap from 夫(550) to 马(900) = 350ms > 300ms, 马 is separate
        #   "虎" at pos 5 with gap=400ms from 马 (not a word)
        service._state.char_commit_times[0] = 100.0  # 中
        service._state.char_commit_times[1] = 150.0  # 国 (gap=50ms, word)
        service._state.char_commit_times[2] = 500.0  # 功 (gap=350ms from 国, separate)
        service._state.char_commit_times[3] = 550.0  # 夫 (gap=50ms, word with 功)
        service._state.char_commit_times[4] = 900.0  # 马 (gap=350ms from 夫, separate)
        service._state.char_commit_times[5] = 1300.0  # 虎 (gap=400ms, not a word)
        rate = service._compute_word_typing_rate()
        # word_chars = 4 (中国 + 功夫), total_cjk = 6
        # rate = 4/6 * 100 = 66.67
        assert round(rate, 2) == pytest.approx(66.67, rel=1e-2)

    def test_mixed_cjk_and_non_cjk(self):
        """混有非 CJK 字符时只计算 CJK"""
        service = TypingService()
        service.set_plain_doc("Hello中国!Good马虎End")
        service.set_total_chars(len("Hello中国!Good马虎End"))
        # CJK positions: 5(中), 6(国), 12(马), 13(虎)
        # 中国: gap=50ms (word)
        # 马虎: gap=400ms (not word)
        service._state.char_commit_times[5] = 100.0
        service._state.char_commit_times[6] = 150.0  # gap=50ms
        service._state.char_commit_times[12] = 200.0
        service._state.char_commit_times[13] = 600.0  # gap=400ms
        rate = service._compute_word_typing_rate()
        # word_chars = 2 (中国), total_cjk = 4
        # rate = 2/4 * 100 = 50.0
        assert rate == 50.0

    def test_gap_exactly_300ms_is_word(self):
        """间隔恰好 300ms 算词组"""
        service = TypingService()
        service.set_plain_doc("中国")
        service.set_total_chars(2)
        service._state.char_commit_times[0] = 100.0
        service._state.char_commit_times[1] = 400.0  # gap=300ms exactly
        assert service._compute_word_typing_rate() == 100.0

    def test_gap_just_over_300ms_not_word(self):
        """间隔恰好 301ms 不算词组"""
        service = TypingService()
        service.set_plain_doc("中国")
        service.set_total_chars(2)
        service._state.char_commit_times[0] = 100.0
        service._state.char_commit_times[1] = 401.0  # gap=301ms > 300ms
        assert service._compute_word_typing_rate() == 0.0
