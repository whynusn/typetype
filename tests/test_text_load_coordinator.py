import random
from unittest.mock import MagicMock

from src.backend.presentation.text_load_coordinator import TextLoadCoordinator


def _make_bridge() -> MagicMock:
    bridge = MagicMock()
    # Signals: make them plain MagicMock objects callable like functions
    bridge.textIdChanged = MagicMock()
    bridge.windowTitleChanged = MagicMock()
    bridge.exitSliceMode = MagicMock()
    bridge.sliceModeChanged = MagicMock()
    bridge.sliceStatusChanged = MagicMock()
    bridge.textLoaded = MagicMock()
    bridge.trainerSegmentLoaded = MagicMock()
    bridge.localArticleSegmentLoaded = MagicMock()
    bridge.wenlaiSegmentLabelChanged = MagicMock()
    return bridge


def _make_coordinator(
    with_wenlai=True, with_local_article=True, with_trainer=True
) -> tuple[TextLoadCoordinator, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    typing = MagicMock()
    text_adapter = MagicMock()
    wenlai = MagicMock() if with_wenlai else None
    local_article = MagicMock() if with_local_article else None
    trainer = MagicMock() if with_trainer else None
    coord = TextLoadCoordinator(
        typing_adapter=typing,
        text_adapter=text_adapter,
        wenlai_adapter=wenlai,
        local_article_adapter=local_article,
        trainer_adapter=trainer,
    )
    return coord, typing, text_adapter, wenlai, local_article, trainer


def _make_segment_result(index=1, total=5, content="测试文本内容"):
    result = MagicMock()
    result.index = index
    result.total = total
    result.content = content
    return result


# ============================================================
# Initialization
# ============================================================

def test_init_sets_defaults():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.pending_standard_source_key == ""
    assert coord.pending_wenlai_score_text == ""
    assert coord.source_slice_backend is None
    assert coord.source_slice_article_id == ""
    assert coord.source_slice_segment_size == 0
    assert coord.source_slice_trainer_id == ""
    assert coord.source_slice_group_size == 0
    assert coord.pending_slice_params["on_fail_action"] == "retype"
    assert coord.pending_slice_params["advance_mode"] == "sequential"
    assert coord.pending_slice_params["pass_count_min"] == 1


def test_init_accepts_none_adapters():
    coord = TextLoadCoordinator(
        typing_adapter=MagicMock(),
        text_adapter=MagicMock(),
        wenlai_adapter=None,
        local_article_adapter=None,
        trainer_adapter=None,
    )
    assert coord._wenlai is None
    assert coord._local_article is None
    assert coord._trainer is None


# ============================================================
# clear_text_id
# ============================================================

def test_clear_text_id_clears_active_and_sets_text_id_zero():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    coord.clear_text_id(bridge)
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)


# ============================================================
# clear_all_sources
# ============================================================

def test_clear_all_sources_clears_all_adapters():
    coord, typing, text_adapter, wenlai, local_article, trainer = _make_coordinator()
    coord.clear_all_sources()
    text_adapter.clear_active.assert_called_once()
    wenlai.clear_active.assert_called_once()
    local_article.clear_active.assert_called_once()
    trainer.clear_active.assert_called_once()


def test_clear_all_sources_skips_none_adapters():
    coord, typing, text_adapter, _, _, _ = _make_coordinator(
        with_wenlai=False, with_local_article=False, with_trainer=False
    )
    coord.clear_all_sources()
    text_adapter.clear_active.assert_called_once()


# ============================================================
# reset_session_for_standard_load
# ============================================================

def test_reset_session_for_standard_load_resets_context_and_text_id():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    coord.reset_session_for_standard_load(bridge)
    typing.reset_session_context.assert_called_once()
    assert bridge._text_id == 0
    bridge.textIdChanged.emit.assert_called_once()


# ============================================================
# prepare_for_wenlai_load
# ============================================================

def test_prepare_for_wenlai_load_clears_slice_and_other_sources():
    coord, typing, text_adapter, wenlai, local_article, trainer = _make_coordinator()
    typing.is_slice_mode.return_value = True
    bridge = _make_bridge()
    coord.prepare_for_wenlai_load(bridge)
    bridge.exitSliceMode.assert_called_once()
    local_article.clear_active.assert_called_once()
    trainer.clear_active.assert_called_once()
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)


def test_prepare_for_wenlai_load_skips_exit_slice_when_not_slice_mode():
    coord, typing, _, wenlai, local_article, trainer = _make_coordinator()
    typing.is_slice_mode.return_value = False
    bridge = _make_bridge()
    coord.prepare_for_wenlai_load(bridge)
    bridge.exitSliceMode.assert_not_called()
    local_article.clear_active.assert_called_once()
    trainer.clear_active.assert_called_once()


# ============================================================
# prepare_for_trainer_load
# ============================================================

def test_prepare_for_trainer_load_clears_slice_and_sets_up_trainer():
    coord, typing, text_adapter, wenlai, local_article, trainer = _make_coordinator()
    typing.is_slice_mode.return_value = True
    local_article.local_article_loading = True
    bridge = _make_bridge()
    coord.prepare_for_trainer_load(bridge)
    bridge.exitSliceMode.assert_called_once()
    wenlai.clear_active.assert_called_once()
    local_article.clear_active.assert_called_once()
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    typing.setup_trainer_session.assert_called_once()


def test_prepare_for_trainer_load_skips_local_article_if_not_loading():
    coord, typing, _, wenlai, local_article, _ = _make_coordinator()
    typing.is_slice_mode.return_value = False
    local_article.local_article_loading = False
    bridge = _make_bridge()
    coord.prepare_for_trainer_load(bridge)
    local_article.clear_active.assert_not_called()


# ============================================================
# prepare_for_local_article_load
# ============================================================

def test_prepare_for_local_article_load_clears_slice_and_other_sources():
    coord, typing, text_adapter, wenlai, local_article, trainer = _make_coordinator()
    typing.is_slice_mode.return_value = True
    bridge = _make_bridge()
    coord.prepare_for_local_article_load(bridge)
    bridge.exitSliceMode.assert_called_once()
    wenlai.clear_active.assert_called_once()
    trainer.clear_active.assert_called_once()
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)


# ============================================================
# on_standard_text_loaded
# ============================================================

def test_on_standard_text_loaded_with_positive_text_id_sets_network_session():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_standard_source_key = "jisubei"
    bridge = _make_bridge()
    coord.on_standard_text_loaded("测试文本", 42, "极速杯", bridge)
    typing.setup_network_session.assert_called_once_with(42, "jisubei")
    typing.setup_local_session.assert_not_called()
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert args[0] == "测试文本"
    assert args[1] == 42
    assert args[2] == "极速杯"


def test_on_standard_text_loaded_with_source_key_sets_local_session():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_standard_source_key = "builtin_demo"
    bridge = _make_bridge()
    coord.on_standard_text_loaded("本地文本", -1, "本地测试", bridge)
    typing.setup_local_session.assert_called_once_with("builtin_demo", None)
    typing.setup_network_session.assert_not_called()


def test_on_standard_text_loaded_without_source_key_skips_session_setup():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_standard_source_key = ""
    bridge = _make_bridge()
    coord.on_standard_text_loaded("文本", 0, "来源", bridge)
    typing.setup_network_session.assert_not_called()
    typing.setup_local_session.assert_not_called()


def test_on_standard_text_loaded_copies_to_clipboard_with_sender():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_standard_source_key = "jisubei"
    bridge = _make_bridge()
    coord.on_standard_text_loaded("测试文本", 1, "极速杯", bridge)
    bridge._copy_text_to_clipboard.assert_called_once()
    sender = bridge._copy_text_to_clipboard.call_args[0][0]
    assert "极速杯" in sender
    assert "测试文本" in sender


def test_on_standard_text_loaded_strips_newlines():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_standard_source_key = "jisubei"
    bridge = _make_bridge()
    coord.on_standard_text_loaded("测试\n文本\r\n", 1, "极速杯", bridge)
    args = bridge.textLoaded.emit.call_args[0]
    assert args[0] == "测试文本"


# ============================================================
# on_wenlai_text_loaded
# ============================================================

def test_on_wenlai_text_loaded_exits_slice_mode_if_needed():
    coord, typing, text_adapter, wenlai, _, _ = _make_coordinator()
    typing.is_slice_mode.return_value = True
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("晴发文内容", "晴发文标题", bridge)
    bridge.exitSliceMode.assert_called_once()
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    typing.setup_wenlai_session.assert_called_once()
    typing.setTextTitle.assert_called_once_with("晴发文标题")
    bridge.windowTitleChanged.emit.assert_called_once()


def test_on_wenlai_text_loaded_not_slice_mode_no_exit():
    coord, typing, _, wenlai, _, _ = _make_coordinator()
    typing.is_slice_mode.return_value = False
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    bridge.exitSliceMode.assert_not_called()


def test_on_wenlai_text_loaded_copies_sender_content():
    coord, typing, _, wenlai, _, _ = _make_coordinator()
    wenlai.current_text.sender_content = "晴发文原文"
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    bridge._copy_text_to_clipboard.assert_called_once()
    clipboard = bridge._copy_text_to_clipboard.call_args[0][0]
    assert clipboard == "晴发文原文"


def test_on_wenlai_text_loaded_appends_score_text():
    coord, typing, _, wenlai, _, _ = _make_coordinator()
    coord._pending_wenlai_score_text = "成绩: 100字/分"
    wenlai.current_text.sender_content = "晴发文原文"
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    clipboard = bridge._copy_text_to_clipboard.call_args[0][0]
    assert "成绩: 100字/分" in clipboard
    assert "晴发文原文" in clipboard


def test_on_wenlai_text_loaded_clears_pending_score_text():
    coord, typing, _, wenlai, _, _ = _make_coordinator()
    coord._pending_wenlai_score_text = "旧成绩"
    wenlai.current_text.sender_content = "内容"
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    assert coord._pending_wenlai_score_text == ""


def test_on_wenlai_text_loaded_emits_signals():
    coord, typing, _, wenlai, _, _ = _make_coordinator()
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    bridge.wenlaiSegmentLabelChanged.emit.assert_called_once()
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert args[0] == "内容"
    assert args[1] == -1
    assert args[2] == "标题"


# ============================================================
# on_trainer_segment_loaded
# ============================================================

def test_on_trainer_segment_loaded_initial_load_sets_up_slice():
    coord, typing, text_adapter, _, _, trainer = _make_coordinator()
    bridge = _make_bridge()
    payload = {
        "title": "练单",
        "index": 1,
        "total": 5,
        "content": "练单文本内容",
        "trainerId": "trainer_001",
        "groupSize": 20,
    }
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    typing.setTextTitle.assert_called_once()
    typing.setup_sourced_slice_mode.assert_called_once()
    typing.set_current_slice_content.assert_called_once_with("练单文本内容")
    args, kwargs = typing.setup_sourced_slice_mode.call_args
    # slice_index and slice_total are positional args
    assert args[0] == 1
    assert args[1] == 5
    assert kwargs.get("slice_size") == 20
    assert kwargs.get("reset_counts") is True


def test_on_trainer_segment_loaded_subsequent_load_does_not_reset_counts():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "trainer"
    typing.slice_index = 2
    bridge = _make_bridge()
    payload = {
        "title": "练单",
        "index": 3,
        "total": 5,
        "content": "第三段",
        "trainerId": "trainer_001",
        "groupSize": 20,
    }
    coord.on_trainer_segment_loaded(payload, bridge)
    _, kwargs = typing.setup_sourced_slice_mode.call_args
    assert kwargs.get("reset_counts") is False


def test_on_trainer_segment_loaded_different_index_resets_pass_count():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "trainer"
    typing.slice_index = 2
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 3, "total": 5, "content": "第三段"}
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.reset_slice_pass_count.assert_called_once_with(3)


def test_on_trainer_segment_loaded_same_index_does_not_reset_pass_count():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "trainer"
    typing.slice_index = 2
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 2, "total": 5, "content": "第二段"}
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.reset_slice_pass_count.assert_not_called()


def test_on_trainer_segment_loaded_emits_signals():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 1, "total": 3, "content": "内容"}
    coord.on_trainer_segment_loaded(payload, bridge)
    bridge.sliceModeChanged.emit.assert_called_once()
    bridge.trainerSegmentLoaded.emit.assert_called_once_with(payload)
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert args[1] == -1
    assert "练单 1/3" in args[2]


def test_on_trainer_segment_loaded_formats_title_with_index():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 2, "total": 5, "content": "内容"}
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.setTextTitle.assert_called_once_with("练单 2/5")


def test_on_trainer_segment_loaded_without_title_uses_bare_index():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "", "index": 2, "total": 5, "content": "内容"}
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.setTextTitle.assert_called_once_with("2/5")


def test_on_trainer_segment_loaded_with_zero_index_skips_slice_setup():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 0, "total": 0, "content": "内容"}
    coord.on_trainer_segment_loaded(payload, bridge)
    typing.setup_sourced_slice_mode.assert_not_called()
    bridge.sliceModeChanged.emit.assert_not_called()


# ============================================================
# on_local_article_segment_loaded
# ============================================================

def test_on_local_article_segment_loaded_initial_load():
    coord, typing, text_adapter, _, local_article, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "文库", "index": 1, "total": 3, "content": "文库内容"}
    coord.source_slice_segment_size = 100
    coord.on_local_article_segment_loaded(payload, bridge)
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    typing.setTextTitle.assert_called_once_with("文库 1/3")
    typing.setup_sourced_slice_mode.assert_called_once()
    pos_args, kwargs = typing.setup_sourced_slice_mode.call_args
    assert pos_args[0] == 1
    assert pos_args[1] == 3
    assert kwargs.get("slice_size") == 100
    assert kwargs.get("reset_counts") is True


def test_on_local_article_segment_loaded_subsequent_no_reset():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    typing.slice_index = 1
    bridge = _make_bridge()
    payload = {"title": "文库", "index": 2, "total": 3, "content": "第二段"}
    coord.on_local_article_segment_loaded(payload, bridge)
    args = typing.setup_sourced_slice_mode.call_args[1]
    assert args["reset_counts"] is False


def test_on_local_article_segment_loaded_resets_pass_count_on_new_index():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    typing.slice_index = 1
    bridge = _make_bridge()
    payload = {"title": "文库", "index": 2, "total": 3, "content": "第二段"}
    coord.on_local_article_segment_loaded(payload, bridge)
    typing.reset_slice_pass_count.assert_called_once_with(2)


def test_on_local_article_segment_loaded_emits_signals():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "文库", "index": 1, "total": 3, "content": "内容"}
    coord.on_local_article_segment_loaded(payload, bridge)
    bridge.sliceModeChanged.emit.assert_called_once()
    bridge.localArticleSegmentLoaded.emit.assert_called_once_with(payload)
    bridge.textLoaded.emit.assert_called_once()


def test_on_local_article_segment_loaded_zero_index_skips_slice():
    coord, typing, _, _, _, _ = _make_coordinator()
    bridge = _make_bridge()
    payload = {"title": "文库", "index": 0, "total": 0, "content": "内容"}
    coord.on_local_article_segment_loaded(payload, bridge)
    typing.setup_sourced_slice_mode.assert_not_called()
    bridge.sliceModeChanged.emit.assert_not_called()


# ============================================================
# load_current_slice
# ============================================================

def test_load_current_slice_loads_by_index():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 2
    typing.slice_total = 5
    typing.get_current_slice_text.return_value = "第二段文本"
    coord._source_slice_title = "练单"
    bridge = _make_bridge()
    coord.load_current_slice(bridge)
    typing.prepare_for_text_load.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    typing.setTextTitle.assert_called_once_with("练单 2/5")
    bridge.windowTitleChanged.emit.assert_called_once()
    bridge.sliceStatusChanged.emit.assert_called_once()
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert args[0] == "第二段文本"
    assert args[1] == -1


def test_load_current_slice_uses_default_label_without_title():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 3
    typing.slice_total = 8
    typing.get_current_slice_text.return_value = "第三段"
    coord._source_slice_title = ""
    bridge = _make_bridge()
    coord.load_current_slice(bridge)
    typing.setTextTitle.assert_called_once_with("载文 3/8")


def test_load_current_slice_returns_early_if_index_out_of_range():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 0
    typing.slice_total = 5
    bridge = _make_bridge()
    coord.load_current_slice(bridge)
    typing.prepare_for_text_load.assert_not_called()


def test_load_current_slice_index_greater_than_total_returns_early():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 6
    typing.slice_total = 5
    bridge = _make_bridge()
    coord.load_current_slice(bridge)
    typing.prepare_for_text_load.assert_not_called()


# ============================================================
# load_next_slice
# ============================================================

def test_load_next_slice_advances_index():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 1
    typing.slice_total = 5
    typing.get_current_slice_text.return_value = "第二段文本"
    coord._source_slice_backend = None
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    typing.reset_slice_pass_count.assert_called_once_with(2)
    typing.set_slice_index.assert_any_call(2)
    typing.restore_slice_metrics.assert_called_once_with(2)


def test_load_next_slice_wraps_around():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 5
    typing.slice_total = 5
    typing.get_current_slice_text.return_value = "第一段文本"
    coord._source_slice_backend = None
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    typing.set_slice_index.assert_any_call(1)


def test_load_next_slice_at_last_with_total_zero_stays_at_one():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 0
    typing.slice_total = 0
    coord._source_slice_backend = None
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    typing.set_slice_index.assert_called_once_with(1)


def test_load_next_slice_trainer_backend_calls_trainer():
    coord, typing, _, _, _, trainer = _make_coordinator()
    coord._source_slice_backend = "trainer"
    coord._source_slice_trainer_id = "trainer_001"
    # Trainer path uses self._trainer.loadNextTrainerSegment() directly,
    # skipping the slice_total/slice_index comparison — but set them to avoid TypeError
    typing.slice_index = 1
    typing.slice_total = 1
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    trainer.loadNextTrainerSegment.assert_called_once()


def test_load_next_slice_local_article_backend_navigates():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    coord._source_slice_title = "文章"
    coord.source_slice_segment_size = 100
    typing.slice_index = 2
    typing.slice_total = 5
    result = _make_segment_result(index=3, total=5, content="第三段")
    text_adapter.get_text_session_segment.return_value = result
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    text_adapter.get_text_session_segment.assert_called_once_with(3)
    typing.setTextTitle.assert_called_once_with("文章 3/5")
    bridge.textLoaded.emit.assert_called_once()


def test_load_next_slice_random_mode_calls_random():
    with _patch_random_choice(1):
        coord, typing, _, _, _, _ = _make_coordinator()
        coord._pending_slice_params["advance_mode"] = "random"
        typing.slice_index = 2
        typing.slice_total = 5
        bridge = _make_bridge()
        coord.load_next_slice(bridge)
        # Should go through load_random_slice path, which calls set_slice_index via load_current_slice
        typing.set_slice_index.assert_any_call(1)


def test_load_next_slice_random_mode_single_slice_does_nothing():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._pending_slice_params["advance_mode"] = "random"
    typing.slice_index = 1
    typing.slice_total = 1
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    # random with total <= 1 returns early
    typing.set_slice_index.assert_not_called()


# ============================================================
# load_prev_slice
# ============================================================

def test_load_prev_slice_goes_back():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 3
    typing.slice_total = 5
    coord._source_slice_backend = None
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    typing.reset_slice_pass_count.assert_called_once_with(2)
    typing.back_slice.assert_called_once()
    typing.restore_slice_metrics.assert_called_once_with(2)


def test_load_prev_slice_at_first_does_nothing():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 1
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    typing.back_slice.assert_not_called()
    typing.reset_slice_pass_count.assert_not_called()


def test_load_prev_slice_at_zero_does_nothing():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 0
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    typing.back_slice.assert_not_called()


def test_load_prev_slice_trainer_backend():
    coord, typing, _, _, _, trainer = _make_coordinator()
    typing.slice_index = 3
    coord._source_slice_backend = "trainer"
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    trainer.loadPreviousTrainerSegment.assert_called_once()


def test_load_prev_slice_local_article_backend():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    coord._source_slice_title = "文章"
    coord.source_slice_segment_size = 100
    typing.slice_index = 3
    result = _make_segment_result(index=2, total=5, content="第二段")
    text_adapter.get_text_session_segment.return_value = result
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    text_adapter.get_text_session_segment.assert_called_once_with(2)


# ============================================================
# load_random_slice
# ============================================================

def test_load_random_slice_selects_unvisited():
    with _patch_random_choice(3):
        coord, typing, _, _, _, _ = _make_coordinator()
        typing.slice_index = 1
        typing.slice_total = 5
        coord._visited_slices = {1, 2}
        coord._source_slice_backend = None
        bridge = _make_bridge()
        coord.load_random_slice(bridge)
        # set_slice_index is called via load_current_slice recursion
        typing.set_slice_index.assert_any_call(3)


def test_load_random_slice_all_visited_resets():
    with _patch_random_choice(5):
        coord, typing, _, _, _, _ = _make_coordinator()
        typing.slice_index = 1
        typing.slice_total = 5
        coord._visited_slices = {1, 2, 3, 4, 5}
        coord._source_slice_backend = None
        bridge = _make_bridge()
        coord.load_random_slice(bridge)
        # After reset, visited should be only {1}
        assert coord._visited_slices == {1}
        # set_slice_index is called via load_current_slice recursion
        typing.set_slice_index.assert_any_call(5)


def test_load_random_slice_single_slice_returns_early():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 1
    typing.slice_total = 1
    bridge = _make_bridge()
    coord.load_random_slice(bridge)
    typing.set_slice_index.assert_not_called()


def test_load_random_slice_total_zero_returns_early():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_total = 0
    bridge = _make_bridge()
    coord.load_random_slice(bridge)
    typing.set_slice_index.assert_not_called()


def test_load_random_slice_trainer_backend():
    with _patch_random_choice(3):
        coord, typing, _, _, _, trainer = _make_coordinator()
        typing.slice_index = 1
        typing.slice_total = 5
        coord._source_slice_backend = "trainer"
        coord._source_slice_trainer_id = "trainer_001"
        bridge = _make_bridge()
        coord.load_random_slice(bridge)
        trainer.setTrainerSegment.assert_called_once_with(3)


def test_load_random_slice_local_article_backend():
    with _patch_random_choice(3):
        coord, typing, text_adapter, _, _, _ = _make_coordinator()
        typing.slice_index = 1
        typing.slice_total = 5
        coord._source_slice_backend = "local_article"
        coord._source_slice_title = "文章"
        coord.source_slice_segment_size = 100
        result = _make_segment_result(index=3, total=5, content="第三段")
        text_adapter.get_text_session_segment.return_value = result
        bridge = _make_bridge()
        coord.load_random_slice(bridge)
        text_adapter.get_text_session_segment.assert_called_once_with(3)


# ============================================================
# handle_slice_retype
# ============================================================

def test_handle_slice_retype_retype_action_non_trainer_local():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = None
    typing.slice_index = 2
    typing.on_fail_action = "retype"
    typing.get_current_slice_text.return_value = "重打文本"
    typing.slice_total = 5
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    typing.prepare_for_text_load.assert_called_once()
    bridge.textLoaded.emit.assert_called_once()


def test_handle_slice_retype_retype_trainer_backend():
    coord, typing, _, _, _, trainer = _make_coordinator()
    coord._source_slice_backend = "trainer"
    typing.on_fail_action = "retype"
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    trainer.loadCurrentTrainerSegment.assert_called_once()


def test_handle_slice_retype_retype_local_article_backend():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    coord._source_slice_title = "文章"
    coord.source_slice_segment_size = 100
    typing.slice_index = 2
    typing.on_fail_action = "retype"
    result = _make_segment_result(index=2, total=5, content="第二段")
    text_adapter.get_text_session_segment.return_value = result
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    text_adapter.get_text_session_segment.assert_called_once_with(2)


def test_handle_slice_retype_shuffle_non_trainer():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.slice_index = 2
    typing.slice_total = 5
    typing.on_fail_action = "shuffle"
    typing.get_shuffled_slice_text.return_value = "乱序文本"
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert "乱序" in args[2]


def test_handle_slice_retype_shuffle_trainer_backend():
    coord, typing, _, _, _, trainer = _make_coordinator()
    coord._source_slice_backend = "trainer"
    typing.on_fail_action = "shuffle"
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    trainer.shuffleCurrentTrainerGroup.assert_called_once()


def test_handle_slice_retype_shuffle_no_shuffled_text_returns_early():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.on_fail_action = "shuffle"
    typing.get_shuffled_slice_text.return_value = ""
    typing.slice_index = 2
    typing.slice_total = 5
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    bridge.textLoaded.emit.assert_not_called()


def test_handle_slice_retype_unknown_action_does_nothing():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.on_fail_action = "advance"
    bridge = _make_bridge()
    coord.handle_slice_retype(bridge)
    # Falls through without calling any backend action
    bridge.textLoaded.emit.assert_not_called()


# ============================================================
# exit_slice_mode
# ============================================================

def test_exit_slice_mode_clears_state():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "trainer"
    coord._source_slice_trainer_id = "trainer_001"
    coord._source_slice_group_size = 20
    coord._visited_slices = {1, 2, 3}
    bridge = _make_bridge()
    coord.exit_slice_mode(bridge)
    assert coord._source_slice_backend is None
    assert coord._source_slice_trainer_id == ""
    assert coord._source_slice_group_size == 0
    assert coord._visited_slices == set()
    typing.exit_slice_mode.assert_called_once()
    bridge.sliceModeChanged.emit.assert_called_once()
    bridge.sliceStatusChanged.emit.assert_called_once_with("")


# ============================================================
# shuffle_current_slice
# ============================================================

def test_shuffle_current_slice_emits_shuffled_text():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    typing.get_shuffled_slice_text.return_value = "乱序文本"
    typing.slice_index = 2
    typing.slice_total = 5
    bridge = _make_bridge()
    coord.shuffle_current_slice(bridge)
    typing.prepare_for_text_load.assert_called_once()
    text_adapter.clear_active.assert_called_once()
    bridge.setTextId.assert_called_once_with(0)
    bridge.textLoaded.emit.assert_called_once()
    args = bridge.textLoaded.emit.call_args[0]
    assert args[0] == "乱序文本"
    assert args[1] == -1
    assert "2/5" in args[2]
    assert "乱序" in args[2]


def test_shuffle_current_slice_no_shuffled_text_returns_early():
    coord, typing, _, _, _, _ = _make_coordinator()
    typing.get_shuffled_slice_text.return_value = ""
    bridge = _make_bridge()
    coord.shuffle_current_slice(bridge)
    bridge.textLoaded.emit.assert_not_called()


# ============================================================
# Properties
# ============================================================

def test_source_slice_backend_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.source_slice_backend is None
    coord.source_slice_backend = "trainer"
    assert coord.source_slice_backend == "trainer"


def test_pending_slice_params_property():
    coord, _, _, _, _, _ = _make_coordinator()
    params = coord.pending_slice_params
    assert params["on_fail_action"] == "retype"
    coord.pending_slice_params = {"on_fail_action": "shuffle"}
    assert coord.pending_slice_params["on_fail_action"] == "shuffle"


def test_pending_standard_source_key_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.pending_standard_source_key == ""
    coord.pending_standard_source_key = "jisubei"
    assert coord.pending_standard_source_key == "jisubei"


def test_pending_wenlai_score_text_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.pending_wenlai_score_text == ""
    coord.pending_wenlai_score_text = "成绩"
    assert coord.pending_wenlai_score_text == "成绩"


def test_source_slice_article_id_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.source_slice_article_id == ""
    coord.source_slice_article_id = "article_123"
    assert coord.source_slice_article_id == "article_123"


def test_source_slice_segment_size_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.source_slice_segment_size == 0
    coord.source_slice_segment_size = 100
    assert coord.source_slice_segment_size == 100


def test_source_slice_trainer_id_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.source_slice_trainer_id == ""
    coord.source_slice_trainer_id = "trainer_001"
    assert coord.source_slice_trainer_id == "trainer_001"


def test_source_slice_group_size_property():
    coord, _, _, _, _, _ = _make_coordinator()
    assert coord.source_slice_group_size == 0
    coord.source_slice_group_size = 20
    assert coord.source_slice_group_size == 20


# ============================================================
# Static helpers
# ============================================================

def test_strip_newlines_removes_newlines():
    assert TextLoadCoordinator._strip_newlines("测试\n文本\r\n") == "测试文本"
    assert TextLoadCoordinator._strip_newlines("无换行") == "无换行"
    assert TextLoadCoordinator._strip_newlines("") == ""


def test_build_local_sender_content_with_all_params():
    result = TextLoadCoordinator._build_local_sender_content("标题", "内容", 2, 5)
    assert "标题" in result
    assert "内容" in result
    assert "段 2/5" in result
    assert "----" in result
    assert "TypeType" in result


def test_build_local_sender_content_zero_index_defaults():
    result = TextLoadCoordinator._build_local_sender_content("标题", "内容", 0, 0)
    assert "段 1/1" in result
    assert "2字" in result


def test_build_local_sender_content_empty_title_returns_empty():
    assert TextLoadCoordinator._build_local_sender_content("", "内容", 1, 3) == ""


def test_build_local_sender_content_empty_content_returns_empty():
    assert TextLoadCoordinator._build_local_sender_content("标题", "", 1, 3) == ""


# ============================================================
# _navigate_local_article (indirectly through public methods)
# ============================================================

def test_navigate_local_article_with_none_segment_returns_early():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    text_adapter.get_text_session_segment.return_value = None
    bridge = _make_bridge()
    coord._navigate_local_article(bridge, 5)
    typing.setTextTitle.assert_not_called()


def test_navigate_local_article_sets_up_properly():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_title = "文章"
    coord.source_slice_segment_size = 100
    typing._session_context = MagicMock()
    result = _make_segment_result(index=2, total=5, content="第二段")
    text_adapter.get_text_session_segment.return_value = result
    bridge = _make_bridge()
    coord._navigate_local_article(bridge, 2)
    typing.setTextTitle.assert_called_once_with("文章 2/5")
    typing.set_current_slice_content.assert_called_once_with("第二段")
    typing.reset_slice_pass_count.assert_called_once_with(2)
    typing.set_slice_index.assert_called_once_with(2)
    typing.restore_slice_metrics.assert_called_once_with(2)
    bridge.sliceModeChanged.emit.assert_called_once()
    bridge.textLoaded.emit.assert_called_once()


def test_navigate_local_article_sets_slice_size_on_context():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_title = "文章"
    coord.source_slice_segment_size = 100
    typing._session_context = MagicMock()
    result = _make_segment_result(index=2, total=5, content="第二段")
    text_adapter.get_text_session_segment.return_value = result
    bridge = _make_bridge()
    coord._navigate_local_article(bridge, 2)
    assert typing._session_context._slice_size == 100


# ============================================================
# _cache_current_content
# ============================================================

def test_cache_current_content_calls_adapter():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._cache_current_content("缓存内容")
    typing.set_current_slice_content.assert_called_once_with("缓存内容")


# ============================================================
# Edge cases for prepare methods with None adapters
# ============================================================

def test_prepare_for_wenlai_load_with_none_local_article_and_trainer():
    coord, typing, _, _, _, _ = _make_coordinator(
        with_wenlai=True, with_local_article=False, with_trainer=False
    )
    typing.is_slice_mode.return_value = False
    bridge = _make_bridge()
    coord.prepare_for_wenlai_load(bridge)
    # Should not crash when optional adapters are None
    typing.prepare_for_text_load.assert_called_once()


def test_prepare_for_trainer_load_with_none_wenlai_and_local_article():
    coord, typing, _, _, _, _ = _make_coordinator(
        with_wenlai=False, with_local_article=False, with_trainer=True
    )
    typing.is_slice_mode.return_value = False
    bridge = _make_bridge()
    coord.prepare_for_trainer_load(bridge)
    typing.prepare_for_text_load.assert_called_once()
    typing.setup_trainer_session.assert_called_once()


def test_prepare_for_local_article_load_with_none_wenlai_and_trainer():
    coord, typing, _, _, _, _ = _make_coordinator(
        with_wenlai=False, with_local_article=True, with_trainer=False
    )
    typing.is_slice_mode.return_value = False
    bridge = _make_bridge()
    coord.prepare_for_local_article_load(bridge)
    typing.prepare_for_text_load.assert_called_once()


# ============================================================
# on_wenlai_text_loaded without wenlai adapter (current_text=None)
# ============================================================

def test_on_wenlai_text_loaded_without_wenlai_adapter():
    coord, typing, text_adapter, _, _, _ = _make_coordinator(with_wenlai=False)
    bridge = _make_bridge()
    coord.on_wenlai_text_loaded("内容", "标题", bridge)
    bridge._copy_text_to_clipboard.assert_not_called()


# ============================================================
# load_next_slice boundary: local_article with None result
# ============================================================

def test_load_next_slice_local_article_none_result_returns_early():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    typing.slice_index = 2
    typing.slice_total = 5
    text_adapter.get_text_session_segment.return_value = None
    bridge = _make_bridge()
    coord.load_next_slice(bridge)
    bridge.textLoaded.emit.assert_not_called()


# ============================================================
# load_prev_slice boundary: local_article with None result
# ============================================================

def test_load_prev_slice_local_article_none_result_returns_early():
    coord, typing, text_adapter, _, _, _ = _make_coordinator()
    coord._source_slice_backend = "local_article"
    typing.slice_index = 3
    text_adapter.get_text_session_segment.return_value = None
    bridge = _make_bridge()
    coord.load_prev_slice(bridge)
    bridge.textLoaded.emit.assert_not_called()


# ============================================================
# Helper
# ============================================================

def _patch_random_choice(return_value):
    """Context manager to patch random.choice to return a predictable value."""
    import unittest.mock as mock

    return mock.patch.object(random, "choice", return_value=return_value)


# Test on_trainer_segment_loaded preserves existing trainerId when payload missing
def test_on_trainer_segment_loaded_preserves_existing_trainer_id():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_trainer_id = "existing_trainer"
    bridge = _make_bridge()
    payload = {"title": "练单", "index": 1, "total": 3, "content": "内容"}
    coord.on_trainer_segment_loaded(payload, bridge)
    assert coord._source_slice_trainer_id == "existing_trainer"


def test_on_trainer_segment_loaded_overrides_trainer_id():
    coord, typing, _, _, _, _ = _make_coordinator()
    coord._source_slice_trainer_id = "old_trainer"
    bridge = _make_bridge()
    payload = {
        "title": "练单",
        "index": 1,
        "total": 3,
        "content": "内容",
        "trainerId": "new_trainer",
    }
    coord.on_trainer_segment_loaded(payload, bridge)
    assert coord._source_slice_trainer_id == "new_trainer"
