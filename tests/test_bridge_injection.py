"""Bridge 架构修复后的注入与代理行为单测。

- _restore_pending_progress 委托 TypingAdapter.restore_slice_progress 并清理自身瞬态
- _make_ott_segment_provider 使用 container 注入的 OttSegmentProvider 实现类
"""

from unittest.mock import MagicMock

from src.backend.presentation.bridge import Bridge


class TestRestorePendingProgressDelegation:
    def test_delegates_to_adapter_and_clears_pending(self):
        typing_adapter = MagicMock()
        bridge = Bridge.__new__(Bridge)
        bridge._typing_adapter = typing_adapter
        rp = {"slice_pass_counts": [1, 0]}
        bridge._pending_restored_progress = rp
        bridge._pending_restore_key = "k"

        bridge._restore_pending_progress()

        typing_adapter.restore_slice_progress.assert_called_once_with(rp)
        assert bridge._pending_restored_progress is None
        assert bridge._pending_restore_key == ""

    def test_empty_pending_is_noop(self):
        typing_adapter = MagicMock()
        bridge = Bridge.__new__(Bridge)
        bridge._typing_adapter = typing_adapter
        bridge._pending_restored_progress = None
        bridge._pending_restore_key = "k"

        bridge._restore_pending_progress()

        typing_adapter.restore_slice_progress.assert_not_called()
        assert bridge._pending_restore_key == "k"  # 未恢复，保留原值

    def test_adapter_without_session_context_still_clears_pending(self):
        """ctx 缺失时原实现会清空 pending；代理路径保持等价行为。"""
        typing_adapter = MagicMock()
        typing_adapter.restore_slice_progress.return_value = None
        bridge = Bridge.__new__(Bridge)
        bridge._typing_adapter = typing_adapter
        rp = {"slice_pass_counts": [1]}
        bridge._pending_restored_progress = rp
        bridge._pending_restore_key = "k"

        bridge._restore_pending_progress()

        typing_adapter.restore_slice_progress.assert_called_once_with(rp)
        assert bridge._pending_restored_progress is None
        assert bridge._pending_restore_key == ""


class TestMakeOttSegmentProviderInjection:
    def test_uses_injected_class(self):
        calls = []

        class FakeProvider:
            def __init__(
                self, adapter, entry_id, revision_id, total_chars, source_segment_size
            ):
                calls.append(
                    (adapter, entry_id, revision_id, total_chars, source_segment_size)
                )

        bridge = Bridge.__new__(Bridge)
        bridge._ott_segment_provider_cls = FakeProvider
        adapter = object()

        provider = bridge._make_ott_segment_provider(adapter, "e1", "r1", 123, 1000)

        assert isinstance(provider, FakeProvider)
        assert calls == [(adapter, "e1", "r1", 123, 1000)]

    def test_falls_back_to_default_class(self):
        from src.backend.integration.ott_segment_provider import OttSegmentProvider

        bridge = Bridge.__new__(Bridge)
        bridge._ott_segment_provider_cls = None
        adapter = object()

        provider = bridge._make_ott_segment_provider(adapter, "e1", "r1", 10, 5)

        assert isinstance(provider, OttSegmentProvider)
        assert provider.get_total_chars() == 10
