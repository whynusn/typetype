"""TypingAdapter.restore_slice_progress 针对性单测。

覆盖 slice_pass_counts / slice_metrics / slice_stats 三分支，
含 None / 空 dict / 越界等边界。
"""

from unittest.mock import MagicMock

from src.backend.application.session_context import TypingSessionContext
from src.backend.presentation.adapters.typing_adapter import TypingAdapter


def _make_adapter(ctx: TypingSessionContext | None) -> TypingAdapter:
    return TypingAdapter(
        typing_service=MagicMock(),
        score_gateway=MagicMock(),
        session_context=ctx,
    )


def _make_ctx() -> TypingSessionContext:
    """9 字符 / slice_size 3 → 3 片的分片会话。"""
    ctx = TypingSessionContext()
    ctx.setup_slice_mode("一二三四五六七八九", 3, 1, 6.0, 100, 95, 1, "retype")
    return ctx


def test_restore_all_three_branches():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)

    rp = {
        "slice_pass_counts": [2, 0, 1],
        "slice_metrics": [
            {"key_stroke_min": 7.0, "speed_min": 110},
            {"key_stroke_min": 6.0, "speed_min": 100},
            {"key_stroke_min": 5.0, "speed_min": 90},
        ],
        "slice_stats": [
            {"speed": 120, "keyAccuracy": 98.0},
            None,
            {"speed": 90, "keyAccuracy": 95.0},
        ],
    }
    adapter.restore_slice_progress(rp)

    assert ctx._slice_pass_counts == [2, 0, 1]
    assert ctx._slice_metrics[0]["key_stroke_min"] == 7.0
    assert ctx._slice_metrics[1]["key_stroke_min"] == 6.0
    assert ctx._slice_metrics[2]["key_stroke_min"] == 5.0
    assert ctx._slice_stats[0] == {"speed": 120, "keyAccuracy": 98.0}
    assert ctx._slice_stats[1] is None
    assert ctx._slice_stats[2] == {"speed": 90, "keyAccuracy": 95.0}
    # restore_slice_metrics(ctx.slice_index) 已应用到当前片标量指标
    assert ctx._key_stroke_min == 7.0
    assert ctx._speed_min == 110


def test_restore_pass_counts_out_of_range_truncated():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)

    adapter.restore_slice_progress({"slice_pass_counts": [5, 6, 7, 8, 9]})

    # 越界条目静默忽略，不改变列表长度
    assert ctx._slice_pass_counts == [5, 6, 7]


def test_restore_metrics_mixed_types_stored_as_is():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)

    adapter.restore_slice_progress(
        {
            "slice_metrics": [
                {"key_stroke_min": 3.0},
                "raw-non-dict",
                42,
                {"key_stroke_min": 99.0},  # 越界：len(ctx._slice_metrics)=3
            ]
        }
    )

    assert ctx._slice_metrics[0] == {"key_stroke_min": 3.0}
    assert ctx._slice_metrics[1] == "raw-non-dict"
    assert ctx._slice_metrics[2] == 42
    assert len(ctx._slice_metrics) == 3


def test_restore_metrics_dict_is_copied_not_referenced():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)
    metric = {"key_stroke_min": 9.0}

    adapter.restore_slice_progress({"slice_metrics": [metric]})

    metric["key_stroke_min"] = 999.0  # 外部修改不应影响 ctx 内已恢复的副本
    assert ctx._slice_metrics[0]["key_stroke_min"] == 9.0


def test_restore_slice_stats_pads_with_none_up_to_slice_total():
    ctx = _make_ctx()  # slice_total = 3，初始 _slice_stats = []
    adapter = _make_adapter(ctx)

    adapter.restore_slice_progress(
        {"slice_stats": [{"speed": 100, "keyAccuracy": 99.0}]}
    )

    assert len(ctx._slice_stats) == 3
    assert ctx._slice_stats[0] == {"speed": 100, "keyAccuracy": 99.0}
    assert ctx._slice_stats[1] is None
    assert ctx._slice_stats[2] is None


def test_restore_slice_stats_out_of_range_truncated():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)

    adapter.restore_slice_progress(
        {"slice_stats": [{"speed": 1}, {"speed": 2}, {"speed": 3}, {"speed": 4}]}
    )

    assert len(ctx._slice_stats) == 3
    assert ctx._slice_stats[2] == {"speed": 3}
    # 第 4 条越界，未写入
    assert all(s != {"speed": 4} for s in ctx._slice_stats)


def test_restore_without_session_context_is_noop():
    adapter = _make_adapter(None)

    # 不抛异常、无副作用
    adapter.restore_slice_progress(
        {"slice_pass_counts": [1, 1], "slice_metrics": [{}], "slice_stats": [{}]}
    )


def test_restore_empty_and_none_values_are_noop():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)
    before_counts = list(ctx._slice_pass_counts)
    before_metrics = [dict(m) for m in ctx._slice_metrics]

    adapter.restore_slice_progress({})
    adapter.restore_slice_progress(
        {
            "slice_pass_counts": None,
            "slice_metrics": None,
            "slice_stats": None,
        }
    )

    assert ctx._slice_pass_counts == before_counts
    assert ctx._slice_metrics == before_metrics
    assert ctx._slice_stats == []


def test_restore_metrics_sets_metrics_without_stats_or_counts():
    ctx = _make_ctx()
    adapter = _make_adapter(ctx)

    adapter.restore_slice_progress({"slice_metrics": [{"speed_min": 130}]})

    # 仅指标分支生效，达标次数/成绩快照不受影响
    assert ctx._speed_min == 130
    assert ctx._slice_pass_counts == [0, 0, 0]
    assert ctx._slice_stats == []
