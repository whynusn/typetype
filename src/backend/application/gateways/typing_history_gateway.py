"""打字历史记录业务网关。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable

from ...ports.typing_history_store import TypingHistoryStore


class TypingHistoryGateway:
    """维护本地持久化的打字历史记录，并提供聚合统计。"""

    MAX_RECORDS = 5000

    def __init__(
        self,
        store: TypingHistoryStore,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self._store = store
        self._today_provider = today_provider

    def append_record(self, record: dict[str, Any]) -> None:
        """追加一条历史记录。"""
        data = self._load_normalized()
        clean = self._normalize_record(record)
        data["records"].insert(0, clean)
        if len(data["records"]) > self.MAX_RECORDS:
            data["records"] = data["records"][: self.MAX_RECORDS]
        self._store.save(data)

    def get_records(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回最近 N 条历史记录。"""
        data = self._load_normalized()
        return list(data["records"][:limit])

    def get_count(self) -> int:
        return len(self._load_normalized()["records"])

    def get_summary(self) -> dict[str, float | int]:
        """返回历史记录聚合摘要。"""
        records = self._load_normalized()["records"]
        total = len(records)
        if total == 0:
            return {
                "total_sessions": 0,
                "average_speed": 0.0,
                "max_speed": 0.0,
                "average_key_accuracy": 0.0,
                "total_chars": 0,
            }

        speeds: list[float] = []
        key_accuracies: list[float] = []
        total_chars = 0
        for r in records:
            speed = r.get("speed")
            if isinstance(speed, (int, float)) and speed >= 0:
                speeds.append(float(speed))
            ka = r.get("keyAccuracy")
            if isinstance(ka, (int, float)) and ka >= 0:
                key_accuracies.append(float(ka))
            total_chars += self._safe_int(r.get("charNum"))

        return {
            "total_sessions": total,
            "average_speed": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
            "max_speed": round(max(speeds), 2) if speeds else 0.0,
            "average_key_accuracy": round(sum(key_accuracies) / len(key_accuracies), 2)
            if key_accuracies
            else 0.0,
            "total_chars": total_chars,
        }

    def get_daily_trend(self, days: int = 30) -> list[dict[str, Any]]:
        """返回最近 days 天每日字数列表（按日期升序）。"""
        records = self._load_normalized()["records"]
        daily: dict[str, int] = defaultdict(int)
        for r in records:
            date_key = self._extract_date_key(r.get("date"))
            if date_key:
                daily[date_key] += self._safe_int(r.get("charNum"))

        today = self._today_provider()
        from datetime import timedelta

        result = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            key = day.isoformat()
            result.append({"date": key, "chars": daily.get(key, 0)})
        return result

    def _load_normalized(self) -> dict[str, Any]:
        data = self._store.load()
        records = data.get("records")
        if not isinstance(records, list):
            records = []
        return {"version": data.get("version", 1), "records": records}

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """清理并补全记录字段。"""
        return {
            "speed": self._safe_float(record.get("speed")),
            "keyStroke": self._safe_float(record.get("keyStroke")),
            "codeLength": self._safe_float(record.get("codeLength")),
            "wrongNum": self._safe_int(record.get("wrongNum")),
            "correctionCount": self._safe_int(record.get("correctionCount")),
            "backspaceCount": self._safe_int(record.get("backspaceCount")),
            "keyAccuracy": self._safe_float(record.get("keyAccuracy")),
            "wordTypingRate": self._safe_float(record.get("wordTypingRate")),
            "biaoDingCount": self._safe_int(record.get("biaoDingCount")),
            "charNum": self._safe_int(record.get("charNum")),
            "time": self._safe_float(record.get("time")),
            "date": record.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "segmentNo": record.get("segmentNo") or "",
            "scoreText": record.get("scoreText") or "",
            "sourceKey": record.get("sourceKey") or "",
            "peakSpeed": self._safe_float(record.get("peakSpeed")),
            "peakKeyStroke": self._safe_float(record.get("peakKeyStroke")),
            "peakCodeLength": self._safe_float(record.get("peakCodeLength")),
            "slowChars": record.get("slowChars") or [],
        }

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_date_key(date_str: Any) -> str | None:
        if not isinstance(date_str, str) or not date_str:
            return None
        # 支持 "2026-07-06 15:00:00" 与 ISO 格式
        parts = date_str.split("T")
        if parts and len(parts[0]) >= 10:
            return parts[0]
        return None
