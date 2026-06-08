"""打词率（word typing rate）计算测试。

判定逻辑：基于输入区文本长度变化（grow_length > 1 = 词组），
而非时间间隔。
"""

from src.backend.domain.services.typing_service import TypingService

import pytest


def _make_service(text: str, phrase_ranges: list[tuple[int, int]] | None = None) -> TypingService:
    """创建带有 phrase_positions 标记的 TypingService。

    phrase_ranges: [(start, end), ...] 标记词组位置区间（含 start, 不含 end）
    """
    service = TypingService()
    service.set_plain_doc(text)
    service.set_total_chars(len(text))
    if phrase_ranges:
        for start, end in phrase_ranges:
            for pos in range(start, end):
                service._state.phrase_positions.add(pos)
    return service


class TestComputeWordTypingRate:
    """测试打词率计算逻辑"""

    def test_empty_document_returns_zero(self):
        service = _make_service("", [])
        assert service._compute_word_typing_rate() == 0.0

    def test_no_cjk_chars_returns_zero(self):
        service = _make_service("hello 123 !!!")
        assert service._compute_word_typing_rate() == 0.0

    def test_no_phrase_positions_returns_zero(self):
        service = _make_service("中国")
        assert service._compute_word_typing_rate() == 0.0

    def test_single_cjk_char_returns_zero(self):
        service = _make_service("一国 二")
        assert service._compute_word_typing_rate() == 0.0

    def test_two_cjk_in_one_phrase(self):
        service = _make_service("中国", [(0, 2)])
        assert service._compute_word_typing_rate() == 100.0

    def test_four_cjk_in_one_phrase(self):
        service = _make_service("中国功夫", [(0, 4)])
        assert service._compute_word_typing_rate() == 100.0

    def test_partial_phrase_rate(self):
        # "中国" 是词组，"功夫" 是词组，"马虎" 是单字
        service = _make_service("中国功夫马虎", [(0, 2), (2, 4)])
        rate = service._compute_word_typing_rate()
        # word_chars = 4, total_cjk = 6
        assert round(rate, 2) == pytest.approx(66.67, rel=1e-2)

    def test_mixed_cjk_and_non_cjk(self):
        # "Hello中国!Good马虎End"
        # CJK positions: 5(中), 6(国), 12(马), 13(虎)
        service = _make_service("Hello中国!Good马虎End", [(5, 7)])
        rate = service._compute_word_typing_rate()
        # word_chars = 2, total_cjk = 4
        assert rate == 50.0

    def test_all_single_chars_returns_zero(self):
        service = _make_service("中国功夫", [])
        assert service._compute_word_typing_rate() == 0.0

    def test_phrase_spanning_non_cjk_boundary(self):
        # "a中国b" - CJK 在 pos 1,2; phrase 标记 pos 1,2
        service = _make_service("a中国b", [(1, 3)])
        assert service._compute_word_typing_rate() == 100.0

    def test_partial_phrase_in_cjk_run(self):
        # "中国功夫" - 只有 "国功" 被标记为词组
        service = _make_service("中国功夫", [(1, 3)])
        rate = service._compute_word_typing_rate()
        # word_chars = 2 (pos 1,2), total_cjk = 4
        assert rate == 50.0

    def test_phrase_positions_ignore_non_cjk(self):
        # "a中国b马虎c" - phrase 标记 pos 1-4 (不含 pos 4)
        # CJK positions: 1(中), 2(国), 4(马), 5(虎)
        # phrase 中的 CJK: pos 1,2 → 2 chars
        service = _make_service("a中国b马虎c", [(1, 4)])
        rate = service._compute_word_typing_rate()
        # word_chars = 2, total_cjk = 4
        assert rate == 50.0

    def test_integration_with_handle_committed_text(self):
        """集成测试：通过 handle_committed_text 模拟真实输入流程"""
        service = TypingService()
        service.set_plain_doc("中国功夫")
        service.set_total_chars(4)

        # 模拟：先打 "中国"（grow_length=2，词组）
        service.handle_committed_text("中国", 2)

        # 模拟：再打 "功夫"（grow_length=2，词组）
        service.handle_committed_text("功夫", 2)

        rate = service._compute_word_typing_rate()
        # 全部 4 个 CJK 字符都在词组中
        assert rate == 100.0
