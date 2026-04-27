from datetime import date
import json

from src.backend.application.gateways.typing_totals_gateway import (
    TypingTotalsGateway,
)
from src.backend.integration.json_typing_totals_store import JsonTypingTotalsStore


class InMemoryTypingTotalsStore:
    def __init__(self, data=None):
        self.data = data or {"total_chars": 0, "daily": {}}

    def load(self):
        return {
            "total_chars": self.data.get("total_chars", 0),
            "daily": dict(self.data.get("daily", {})),
        }

    def save(self, data):
        self.data = data


def test_typing_totals_records_today_and_total_chars():
    store = InMemoryTypingTotalsStore()
    gateway = TypingTotalsGateway(store, today_provider=lambda: date(2026, 4, 26))

    gateway.record_session(120)
    gateway.record_session(30)

    assert gateway.today_chars == 150
    assert gateway.total_chars == 150
    assert store.data == {"total_chars": 150, "daily": {"2026-04-26": 150}}


def test_typing_totals_ignores_non_positive_char_counts():
    store = InMemoryTypingTotalsStore()
    gateway = TypingTotalsGateway(store, today_provider=lambda: date(2026, 4, 26))

    gateway.record_session(0)
    gateway.record_session(-3)

    assert gateway.today_chars == 0
    assert gateway.total_chars == 0


def test_json_typing_totals_store_persists_counts_to_disk(tmp_path):
    path = tmp_path / "typing_totals.json"
    gateway = TypingTotalsGateway(
        JsonTypingTotalsStore(path),
        today_provider=lambda: date(2026, 4, 26),
    )

    gateway.record_session(86)

    reloaded = TypingTotalsGateway(
        JsonTypingTotalsStore(path),
        today_provider=lambda: date(2026, 4, 26),
    )
    assert reloaded.today_chars == 86
    assert reloaded.total_chars == 86
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "total_chars": 86,
        "daily": {"2026-04-26": 86},
    }
