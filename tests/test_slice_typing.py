"""测试分片载文模式下的 TypingService 行为。

验证分片切换时状态正确重置，与全文载文行为一致。
"""

from src.backend.domain.services.typing_service import TypingService


def test_slice_switch_resets_state():
    """模拟分片切换：打完一片后，加载下一片，验证状态正确重置。"""
    service = TypingService()

    # === 第一片 ===
    text1 = "你好世界"
    service.set_total_chars(len(text1))
    service.set_plain_doc(text1)
    service.clear()
    service.start()

    # 打完第一片
    updates, completed = service.handle_committed_text("你好世界", 4)
    assert completed
    assert service.score_data.char_count == 4
    assert service.score_data.wrong_char_count == 0

    # === 分片切换：模拟 prepare_for_text_load + handleLoadedText ===
    service.stop()
    service.clear()
    service.set_text_id(None)
    service.set_read_only(True)

    # handleLoadedText 中会执行:
    text2 = "测试分片"
    service.set_total_chars(len(text2))  # 这会归零 char_count
    service.set_plain_doc(text2)
    service.clear()
    service.state.is_started = False
    service.set_read_only(False)

    # 验证状态已重置
    assert service.state.score_data.char_count == 0
    assert service.state.score_data.wrong_char_count == 0
    assert service.state.total_chars == 4
    assert service.state.plain_doc == "测试分片"
    assert not service.state.is_started
    assert not service.state.is_read_only

    # === 第二片开始打字 ===
    service.start()

    # 打第一个字
    updates, _ = service.handle_committed_text("测", 1)
    assert len(updates) == 1
    assert updates[0] == (0, "测", False)  # pos=0, char=测, not error
    assert service.score_data.char_count == 1

    # 打完第二片
    updates2, completed2 = service.handle_committed_text("试分片", 3)
    assert completed2
    assert service.score_data.char_count == 4
    assert service.score_data.wrong_char_count == 0


def test_slice_switch_with_errors():
    """分片切换前有错误，切换后错误计数正确重置。"""
    service = TypingService()

    # === 第一片（有错误） ===
    text1 = "你好世界"
    service.set_total_chars(len(text1))
    service.set_plain_doc(text1)
    service.clear()
    service.start()

    # 打错第一个字
    updates, _ = service.handle_committed_text("你坏世界", 4)
    assert service.score_data.wrong_char_count == 1  # "坏" != "好"
    assert service.score_data.char_count == 4

    # === 分片切换 ===
    service.stop()
    service.clear()
    service.set_text_id(None)
    service.set_read_only(True)

    text2 = "测试"
    service.set_total_chars(len(text2))
    service.set_plain_doc(text2)
    service.clear()
    service.state.is_started = False
    service.set_read_only(False)

    # 错误计数应该已归零
    assert service.score_data.wrong_char_count == 0
    assert service.score_data.char_count == 0

    # 第二片打字
    service.start()
    updates, _ = service.handle_committed_text("测", 1)
    assert updates[0] == (0, "测", False)
    assert service.score_data.char_count == 1
    assert service.score_data.wrong_char_count == 0


def test_begin_pos_after_slice_switch():
    """分片切换后 begin_pos 计算正确，不会出现负数。"""
    service = TypingService()

    # === 第一片（30字） ===
    text1 = "一" * 30
    service.set_total_chars(len(text1))
    service.set_plain_doc(text1)
    service.clear()
    service.start()

    # 打完第一片
    updates, completed = service.handle_committed_text(text1, 30)
    assert completed
    assert service.score_data.char_count == 30

    # === 分片切换 ===
    service.stop()
    service.clear()
    service.set_text_id(None)
    service.set_read_only(True)

    text2 = "二" * 20
    service.set_total_chars(len(text2))
    service.set_plain_doc(text2)
    service.clear()
    service.state.is_started = False
    service.set_read_only(False)

    # 第二片打第一个字
    service.start()
    updates, _ = service.handle_committed_text("二", 1)

    # begin_pos 应该是 0，不是 30
    assert len(updates) == 1
    assert updates[0][0] == 0  # pos = 0
    assert service.score_data.char_count == 1


def test_delete_after_slice_switch():
    """分片切换后删除字符不会出现负位置。"""
    service = TypingService()

    # === 第一片 ===
    text1 = "一" * 30
    service.set_total_chars(len(text1))
    service.set_plain_doc(text1)
    service.clear()
    service.start()
    service.handle_committed_text(text1, 30)

    # === 分片切换 ===
    service.stop()
    service.clear()
    service.set_read_only(True)

    text2 = "二" * 20
    service.set_total_chars(len(text2))
    service.set_plain_doc(text2)
    service.clear()
    service.state.is_started = False
    service.set_read_only(False)

    # 第二片打几个字然后删除
    service.start()
    service.handle_committed_text("二二二", 3)
    assert service.score_data.char_count == 3

    # 删除一个字
    updates, _ = service.handle_committed_text("", -1)
    # 不应该有负位置
    for pos, char, is_error in updates:
        assert pos >= 0, f"负位置: {pos}"
    assert service.score_data.char_count == 2
