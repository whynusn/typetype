from unittest.mock import MagicMock

from src.backend.presentation.adapters.char_stats_adapter import CharStatsAdapter


def test_on_weak_chars_loaded_discards_stale_signature():
    adapter = CharStatsAdapter(char_stats_service=MagicMock())
    emitted: list[list[dict]] = []
    adapter.weakestCharsLoaded.connect(emitted.append)

    adapter._latest_requested = (10, "error_rate", None)  # type: ignore[attr-defined]

    adapter._on_weak_chars_loaded(  # type: ignore[attr-defined]
        [{"ch": "新"}], (10, "error_rate", None)
    )
    adapter._on_weak_chars_loaded(  # type: ignore[attr-defined]
        [{"ch": "旧"}], (10, "error_count", None)
    )

    assert emitted == [[{"ch": "新"}]]


def test_on_weak_chars_loaded_triggers_rerun_when_flagged():
    adapter = CharStatsAdapter(char_stats_service=MagicMock())
    called = []

    def fake_dispatch() -> None:
        called.append(1)

    adapter._dispatch_weak_chars_query = fake_dispatch  # type: ignore[attr-defined]
    adapter._latest_requested = (10, "error_rate", None)  # type: ignore[attr-defined]
    adapter._rerun_after_inflight = True  # type: ignore[attr-defined]
    adapter._inflight = True  # type: ignore[attr-defined]

    adapter._on_weak_chars_loaded(  # type: ignore[attr-defined]
        [{"ch": "新"}], (10, "error_rate", None)
    )

    assert called == [1]
