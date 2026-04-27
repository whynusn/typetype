"""测试 TypingSessionContext 状态机。"""

from src.backend.application.session_context import (
    SessionPhase,
    SourceMode,
    UploadStatus,
    TypingSessionContext,
)


def _setup_slice(ctx: TypingSessionContext, total: int = 3) -> None:
    """辅助函数：快速设置分片会话。"""
    ctx.setup_slice_mode("a" * total, 1, 1, 0, 0, 0, 1, "retype")


class TestSessionPhaseTransitions:
    def test_initial_state(self):
        ctx = TypingSessionContext()
        assert ctx.phase == SessionPhase.IDLE
        assert ctx.source_mode is None
        assert ctx.upload_status == UploadStatus.NA

    def test_setup_network_goes_to_ready(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        assert ctx.phase == SessionPhase.READY

    def test_ready_to_typing(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        ctx.start_typing()
        assert ctx.phase == SessionPhase.TYPING

    def test_typing_to_completed(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        ctx.start_typing()
        ctx.complete_typing()
        assert ctx.phase == SessionPhase.COMPLETED

    def test_reset_goes_to_idle(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        ctx.start_typing()
        ctx.complete_typing()
        ctx.reset()
        assert ctx.phase == SessionPhase.IDLE
        assert ctx.source_mode is None

    def test_start_typing_from_idle_ignored(self):
        ctx = TypingSessionContext()
        ctx.start_typing()
        assert ctx.phase == SessionPhase.IDLE

    def test_complete_typing_from_ready_ignored(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        ctx.complete_typing()
        assert ctx.phase == SessionPhase.READY


class TestUploadStatusDerivation:
    def test_network_session_confirmed(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        assert ctx.upload_status == UploadStatus.CONFIRMED

    def test_local_session_with_text_id(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local", text_id=10)
        assert ctx.upload_status == UploadStatus.CONFIRMED

    def test_local_session_without_text_id_pending(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        assert ctx.upload_status == UploadStatus.PENDING

    def test_custom_session_pending(self):
        ctx = TypingSessionContext()
        ctx.setup_custom_session(source_key="custom")
        assert ctx.upload_status == UploadStatus.PENDING

    def test_clipboard_session_na(self):
        ctx = TypingSessionContext()
        ctx.setup_clipboard_session()
        assert ctx.upload_status == UploadStatus.NA

    def test_slice_session_na(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=5)
        assert ctx.upload_status == UploadStatus.NA

    def test_shuffle_session_na(self):
        ctx = TypingSessionContext()
        ctx.setup_shuffle_session()
        assert ctx.upload_status == UploadStatus.NA

    def test_wenlai_session_na(self):
        ctx = TypingSessionContext()
        ctx.setup_wenlai_session()
        assert ctx.upload_status == UploadStatus.NA

    def test_local_article_session_na(self):
        ctx = TypingSessionContext()
        ctx.setup_local_article_session()
        assert ctx.source_mode == SourceMode.LOCAL_ARTICLE
        assert ctx.upload_status == UploadStatus.NA
        assert ctx.can_submit_score() is False

    def test_trainer_session_na(self):
        ctx = TypingSessionContext()
        ctx.setup_trainer_session()
        assert ctx.source_mode == SourceMode.TRAINER
        assert ctx.upload_status == UploadStatus.NA
        assert ctx.can_submit_score() is False


class TestSetTextId:
    def test_pending_to_confirmed(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        assert ctx.upload_status == UploadStatus.PENDING

        ctx.set_text_id(42)
        assert ctx.upload_status == UploadStatus.CONFIRMED
        assert ctx.text_id == 42

    def test_pending_to_ineligible_on_none(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        ctx.set_text_id(None)
        assert ctx.upload_status == UploadStatus.INELIGIBLE

    def test_pending_to_ineligible_on_zero(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        ctx.set_text_id(0)
        assert ctx.upload_status == UploadStatus.INELIGIBLE

    def test_custom_session_resolved(self):
        ctx = TypingSessionContext()
        ctx.setup_custom_session(source_key="custom")
        assert ctx.upload_status == UploadStatus.PENDING

        ctx.set_text_id(99)
        assert ctx.upload_status == UploadStatus.CONFIRMED

    def test_na_stays_na(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=3)
        ctx.set_text_id(42)
        assert ctx.upload_status == UploadStatus.NA


class TestCanSubmitScore:
    def test_confirmed_can_submit(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        assert ctx.can_submit_score() is True

    def test_pending_cannot_submit(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        assert ctx.can_submit_score() is False

    def test_na_cannot_submit(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=5)
        assert ctx.can_submit_score() is False

    def test_ineligible_cannot_submit(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        ctx.set_text_id(None)
        assert ctx.can_submit_score() is False


class TestEligibilityReason:
    def test_slice_reason(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=5)
        assert "分片" in ctx.get_eligibility_reason()

    def test_shuffle_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_shuffle_session()
        assert "乱序" in ctx.get_eligibility_reason()

    def test_clipboard_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_clipboard_session()
        assert "剪贴板" in ctx.get_eligibility_reason()

    def test_confirmed_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_network_session(text_id=42, source_key="jisubei")
        assert "提交排行榜" in ctx.get_eligibility_reason()

    def test_pending_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_local_session(source_key="local")
        assert "确认" in ctx.get_eligibility_reason()

    def test_wenlai_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_wenlai_session()
        assert ctx.get_eligibility_reason() == "晴发文文本，成绩不提交排行榜"

    def test_local_article_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_local_article_session()
        assert ctx.get_eligibility_reason() == "本地长文，成绩不提交排行榜"

    def test_trainer_reason(self):
        ctx = TypingSessionContext()
        ctx.setup_trainer_session()
        assert ctx.get_eligibility_reason() == "练单器，成绩不提交排行榜"


class TestAdvanceSlice:
    def test_advance_updates_index(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=3)
        assert ctx.slice_index == 1

        ctx.start_typing()
        ctx.complete_typing()
        ctx.advance_slice()
        assert ctx.slice_index == 2
        assert ctx.phase == SessionPhase.READY

    def test_advance_does_not_exceed_total(self):
        ctx = TypingSessionContext()
        _setup_slice(ctx, total=2)
        ctx._slice_index = 2
        ctx.advance_slice()
        assert ctx.slice_index == 2  # 不变


class TestSubscriptions:
    def test_upload_status_notification(self):
        changes: list[UploadStatus] = []
        ctx = TypingSessionContext()
        ctx.subscribe_upload_status(lambda s: changes.append(s))

        ctx.setup_local_session(source_key="local")
        assert changes == [UploadStatus.PENDING]

        ctx.set_text_id(42)
        assert changes == [UploadStatus.PENDING, UploadStatus.CONFIRMED]

    def test_eligibility_reason_notification(self):
        reasons: list[str] = []
        ctx = TypingSessionContext()
        ctx.subscribe_eligibility_reason(lambda r: reasons.append(r))

        ctx.setup_network_session(text_id=42, source_key="jisubei")
        assert len(reasons) == 1
        assert "提交排行榜" in reasons[0]

    def test_no_duplicate_notification(self):
        changes: list[UploadStatus] = []
        ctx = TypingSessionContext()
        ctx.subscribe_upload_status(lambda s: changes.append(s))

        # 初始已是 NA，setup_slice 推导也是 NA，不通知（无变化）
        _setup_slice(ctx, total=3)
        assert len(changes) == 0

        # 从 NA 变为 CONFIRMED 才通知
        ctx.reset()
        ctx.setup_network_session(text_id=42, source_key="k")
        assert len(changes) == 1
        assert changes[0] == UploadStatus.CONFIRMED


class TestSliceMode:
    def test_setup_slice_mode(self):
        ctx = TypingSessionContext()
        total = ctx.setup_slice_mode("hello world", 3, 1, 0, 0, 0, 1, "retype")
        assert total == 4  # "hel" "lo " "wor" "ld"
        assert ctx.slice_index == 1
        assert ctx.slice_total == 4
        assert ctx.source_mode.name == "SLICE"

    def test_get_current_slice_text(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abcd", 2, 1, 0, 0, 0, 1, "retype")
        assert ctx.get_current_slice_text() == "ab"
        ctx.advance_slice()
        assert ctx.get_current_slice_text() == "cd"

    def test_is_last_slice(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("ab", 1, 1, 0, 0, 0, 1, "retype")
        assert not ctx.is_last_slice()  # 第1/2片
        ctx.advance_slice()
        assert ctx.is_last_slice()  # 第2/2片

    def test_should_retype(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 100, 0, 1, "retype")
        ctx.collect_slice_result(
            {"speed": 50, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is True

    def test_should_not_retype(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 100, 0, 1, "retype")
        ctx.collect_slice_result(
            {"speed": 120, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is False

    def test_should_retype_with_wrong_chars(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 0, 0, 1, "retype")
        ctx.collect_slice_result(
            {"speed": 100, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 1}
        )
        assert ctx.should_retype() is True

    def test_on_fail_action_none_never_retypes(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 100, 100, 95, 5, "none")
        ctx.collect_slice_result(
            {"speed": 50, "keyAccuracy": 50, "keyStroke": 2, "wrong_char_count": 5}
        )
        assert ctx.should_retype() is False

    def test_get_slice_status(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 0, 0, 1, "retype")
        assert "第 1/3" in ctx.get_slice_status()
        ctx.collect_slice_result(
            {"speed": 80, "keyAccuracy": 95.5, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert "80CPM" in ctx.get_slice_status()
        assert "95.5%" in ctx.get_slice_status()

    def test_get_aggregate_data(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("ab", 1, 1, 0, 0, 0, 1, "retype")
        ctx.collect_slice_result(
            {"speed": 80, "keyStroke": 5, "keyAccuracy": 95, "wrong_char_count": 0}
        )
        data = ctx.get_aggregate_data()
        assert data is not None
        assert data[1] == 1  # 只有1片有成绩

    def test_get_last_slice_stats(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("ab", 1, 1, 0, 0, 0, 1, "retype")
        assert ctx.get_last_slice_stats() == {}
        ctx.collect_slice_result(
            {"speed": 80, "keyStroke": 5, "keyAccuracy": 95, "wrong_char_count": 0}
        )
        assert ctx.get_last_slice_stats()["speed"] == 80

    def test_collect_slice_result_overwrites_same_slice_retry(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("ab", 1, 1, 0, 0, 0, 1, "retype")
        ctx.collect_slice_result(
            {"speed": 40, "keyAccuracy": 90, "keyStroke": 3, "wrong_char_count": 0}
        )
        ctx.collect_slice_result(
            {"speed": 75, "keyAccuracy": 98, "keyStroke": 8, "wrong_char_count": 0}
        )

        data = ctx.get_aggregate_data()
        assert data is not None
        assert len(data[0]) == 1
        assert data[0][0]["speed"] == 75

    def test_exit_slice_mode(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 0, 0, 1, "retype")
        ctx.exit_slice_mode()
        assert ctx.phase == SessionPhase.IDLE
        assert ctx.slice_total == 0
        assert ctx.get_current_slice_text() == ""

    def test_on_fail_action_property(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("abc", 1, 1, 0, 0, 0, 1, "shuffle")
        assert ctx.on_fail_action == "shuffle"

    def test_pass_count_per_slice(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode("ab", 1, 1, 0, 100, 0, 2, "retype")
        # 第1片重打累积：达标2次后合格
        ctx.collect_slice_result(
            {"speed": 120, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is True  # pass_count[0]=1 < 2
        ctx.collect_slice_result(
            {"speed": 110, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is False  # pass_count[0]=2 >= 2 → 第1片达标

        # 推进到第2片
        ctx.start_typing()
        ctx.complete_typing()
        ctx.advance_slice()
        assert ctx.slice_index == 2

        # 第2片从0开始累积达标次数
        ctx.collect_slice_result(
            {"speed": 120, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is True  # pass_count[1]=1 < 2（与第1片独立）
        ctx.collect_slice_result(
            {"speed": 120, "keyAccuracy": 95, "keyStroke": 5, "wrong_char_count": 0}
        )
        assert ctx.should_retype() is False  # pass_count[1]=2 >= 2
