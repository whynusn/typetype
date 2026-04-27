from collections.abc import Callable
from datetime import date
from typing import Any

from ...ports.typing_totals_store import TypingTotalsStore


class TypingTotalsGateway:
    """维护已完成跟打的今日字数和总字数。"""

    def __init__(
        self,
        store: TypingTotalsStore,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self._store = store
        self._today_provider = today_provider

    @property
    def today_chars(self) -> int:
        data = self._load_normalized()
        return data["daily"].get(self._today_key(), 0)

    @property
    def total_chars(self) -> int:
        return self._load_normalized()["total_chars"]

    def record_session(self, char_count: int) -> None:
        if char_count <= 0:
            return
        data = self._load_normalized()
        today_key = self._today_key()
        data["total_chars"] += char_count
        data["daily"][today_key] = data["daily"].get(today_key, 0) + char_count
        self._store.save(data)

    def _today_key(self) -> str:
        return self._today_provider().isoformat()

    def _load_normalized(self) -> dict[str, Any]:
        raw = self._store.load()
        daily_raw = raw.get("daily", {})
        daily = daily_raw if isinstance(daily_raw, dict) else {}
        return {
            "total_chars": self._safe_int(raw.get("total_chars")),
            "daily": {str(k): self._safe_int(v) for k, v in daily.items()},
        }

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0
