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


def test_random_slice_visited_tracking():
    """随机模式下已访问片段不应重复选择，全部访问后重置。"""
    import random

    random.seed(42)

    total = 5
    visited: set[int] = set()
    current = 1
    results = []

    for _ in range(total * 3):
        visited.add(current)
        unvisited = [i for i in range(1, total + 1) if i not in visited]
        if not unvisited:
            visited = {current}
            unvisited = [i for i in range(1, total + 1) if i != current]
        if not unvisited:
            break
        next_idx = random.choice(unvisited)
        results.append(next_idx)
        current = next_idx

    # 前 4 次应不重复（覆盖全部 5 片中的 4 个新片段）
    first_cycle = results[: total - 1]
    assert len(set(first_cycle)) == total - 1, f"首轮出现重复: {first_cycle}"

    # 第 5 次应触发重置，开始新一轮
    assert len(results) > total - 1


def test_decrease_metrics_reset_on_slice_switch():
    """降击后切换到下一段时，指标应恢复为该段的初始值。"""
    from src.backend.application.session_context import TypingSessionContext

    ctx = TypingSessionContext()
    text = "一" * 60
    ctx.setup_slice_mode(
        text=text,
        slice_size=20,
        start_slice=1,
        key_stroke_min=6.0,
        speed_min=100,
        accuracy_min=95,
        pass_count_min=1,
        on_fail_action="retype",
        auto_decrease_enabled=True,
        key_stroke_decrease=0.5,
        speed_decrease=10,
        accuracy_decrease=5,
    )

    # 第一段初始指标
    assert ctx._key_stroke_min == 6.0
    assert ctx._speed_min == 100
    assert ctx._accuracy_min == 95

    # 模拟第一段失败降击
    ctx.decrease_metrics_on_fail()
    assert ctx._key_stroke_min == 5.5
    assert ctx._speed_min == 90
    assert ctx._accuracy_min == 90

    # 切换到第二段（模拟 load_next_slice 的实际顺序：先切索引，再恢复指标）
    ctx._slice_index = 2
    ctx.restore_slice_metrics(2)
    assert ctx._key_stroke_min == 6.0, f"击键未恢复: {ctx._key_stroke_min}"
    assert ctx._speed_min == 100, f"速度未恢复: {ctx._speed_min}"
    assert ctx._accuracy_min == 95, f"准确率未恢复: {ctx._accuracy_min}"

    # 第二段独立降击
    ctx.decrease_metrics_on_fail()
    assert ctx._key_stroke_min == 5.5
    ctx.decrease_metrics_on_fail()
    assert ctx._key_stroke_min == 5.0

    # 切回第一段，应恢复第一段降击后的值（5.5），而非第二段的（5.0）
    ctx._slice_index = 1
    ctx.restore_slice_metrics(1)
    assert ctx._key_stroke_min == 5.5, f"第一段指标未正确恢复: {ctx._key_stroke_min}"
    assert ctx._speed_min == 90
    assert ctx._accuracy_min == 90


def test_restore_progress_preserves_unvisited_slice_metrics():
    """恢复进度后，未访问片段应保持原始指标，非降击后的全局值。"""
    from src.backend.application.session_context import TypingSessionContext

    ctx = TypingSessionContext()
    text = "一" * 60
    ctx.setup_slice_mode(
        text=text,
        slice_size=20,
        start_slice=1,
        key_stroke_min=6.0,
        speed_min=100,
        accuracy_min=95,
        pass_count_min=1,
        on_fail_action="retype",
        auto_decrease_enabled=True,
        key_stroke_decrease=0.5,
        speed_decrease=10,
        accuracy_decrease=5,
    )

    # 第一段降击一次
    ctx.decrease_metrics_on_fail()
    assert ctx._key_stroke_min == 5.5

    # 保存进度（模拟退出）
    saved_slice_metrics = [m.copy() for m in ctx._slice_metrics]
    saved_metrics = {
        "key_stroke_min": ctx._key_stroke_min,
        "speed_min": ctx._speed_min,
        "accuracy_min": ctx._accuracy_min,
        "pass_count_min": ctx._pass_count_min,
        "on_fail_action": ctx._on_fail_action,
        "auto_decrease_enabled": ctx._auto_decrease_enabled,
        "key_stroke_decrease": ctx._key_stroke_decrease,
        "speed_decrease": ctx._speed_decrease,
        "accuracy_decrease": ctx._accuracy_decrease,
    }

    # 模拟恢复进度：用原始用户指标初始化，再覆盖 per-slice
    ctx2 = TypingSessionContext()
    ctx2.setup_slice_mode(
        text=text,
        slice_size=20,
        start_slice=1,
        key_stroke_min=6.0,  # 原始用户指标
        speed_min=100,
        accuracy_min=95,
        pass_count_min=1,
        on_fail_action="retype",
        auto_decrease_enabled=True,
        key_stroke_decrease=0.5,
        speed_decrease=10,
        accuracy_decrease=5,
    )
    # 恢复保存的标量指标和 per-slice 指标
    ctx2._apply_metrics_dict(saved_metrics)
    ctx2._slice_metrics = [m.copy() for m in saved_slice_metrics]

    # 第一段应有降击后的值
    ctx2._slice_index = 1
    ctx2.restore_slice_metrics(1)
    assert ctx2._key_stroke_min == 5.5, f"第一段应为降击值: {ctx2._key_stroke_min}"

    # 第二段应保持原始值（未访问过）
    ctx2._slice_index = 2
    ctx2.restore_slice_metrics(2)
    assert ctx2._key_stroke_min == 6.0, f"第二段应为原始值: {ctx2._key_stroke_min}"
    assert ctx2._speed_min == 100
    assert ctx2._accuracy_min == 95
