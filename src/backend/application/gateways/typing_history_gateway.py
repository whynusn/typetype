"""打字历史记录业务网关。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from ...ports.typing_history_store import TypingHistoryStore


class TypingHistoryGateway:
    """维护本地持久化的打字历史记录，并提供聚合统计。"""

    def __init__(
        self,
        store: TypingHistoryStore,
        max_records: int = 2000,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self._store = store
        self._max_records = max_records
        self._today_provider = today_provider

    def append_record(self, record: dict[str, Any]) -> None:
        """追加一条历史记录。"""
        data = self._load_normalized()
        clean = self._normalize_record(record)
        data["records"].insert(0, clean)
        if len(data["records"]) > self._max_records:
            data["records"] = data["records"][: self._max_records]
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

    def get_trend(self, period: str = "day") -> list[dict[str, Any]]:
        """返回指定粒度的字数趋势（按时间升序）。"""
        if period == "hour":
            return self._get_hourly_trend()
        if period == "week":
            return self._get_weekly_trend()
        if period == "month":
            return self._get_monthly_trend()
        return self.get_daily_trend()

    def get_daily_trend(self, days: int = 30) -> list[dict[str, Any]]:
        """返回最近 days 天每日字数列表（按日期升序）。"""
        records = self._load_normalized()["records"]
        daily: dict[str, int] = defaultdict(int)
        for r in records:
            date_key = self._extract_date_key(r.get("date"))
            if date_key:
                daily[date_key] += self._safe_int(r.get("charNum"))

        today = self._today_provider()

        result = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            key = day.isoformat()
            result.append({"date": key, "period": "day", "chars": daily.get(key, 0)})
        return result

    def _get_hourly_trend(self) -> list[dict[str, Any]]:
        records = self._load_normalized()["records"]
        hourly: dict[str, int] = defaultdict(int)
        for r in records:
            dt = self._parse_record_datetime(r.get("date"))
            if dt:
                hourly[dt.strftime("%Y-%m-%d %H:00")] += self._safe_int(
                    r.get("charNum")
                )

        today_start = datetime.combine(self._today_provider(), time.min)
        result = []
        for i in range(24):
            hour = today_start + timedelta(hours=i)
            key = hour.strftime("%Y-%m-%d %H:00")
            result.append({"date": key, "period": "hour", "chars": hourly.get(key, 0)})
        return result

    def _get_weekly_trend(self, weeks: int = 12) -> list[dict[str, Any]]:
        records = self._load_normalized()["records"]
        weekly: dict[str, int] = defaultdict(int)
        for r in records:
            dt = self._parse_record_datetime(r.get("date"))
            if dt:
                weekly[self._iso_week_key(dt.date())] += self._safe_int(
                    r.get("charNum")
                )

        current_week_start = self._today_provider() - timedelta(
            days=self._today_provider().weekday()
        )
        result = []
        for i in range(weeks - 1, -1, -1):
            week_start = current_week_start - timedelta(weeks=i)
            key = self._iso_week_key(week_start)
            result.append({"date": key, "period": "week", "chars": weekly.get(key, 0)})
        return result

    def _get_monthly_trend(self, months: int = 12) -> list[dict[str, Any]]:
        records = self._load_normalized()["records"]
        monthly: dict[str, int] = defaultdict(int)
        for r in records:
            dt = self._parse_record_datetime(r.get("date"))
            if dt:
                monthly[dt.strftime("%Y-%m")] += self._safe_int(r.get("charNum"))

        today = self._today_provider()
        result = []
        for i in range(months - 1, -1, -1):
            month = self._shift_month(today.year, today.month, -i)
            key = f"{month[0]:04d}-{month[1]:02d}"
            result.append(
                {"date": key, "period": "month", "chars": monthly.get(key, 0)}
            )
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
        # 支持 "2026-07-06 15:00:00"（空格）与 "2026-07-06T15:00:00"（ISO）格式
        parts = date_str.split("T")
        raw = parts[0] if parts else date_str
        # 统一截取前 10 个字符作为日期键
        if len(raw) >= 10:
            return raw[:10]
        return None

    @staticmethod
    def _parse_record_datetime(date_str: Any) -> datetime | None:
        if not isinstance(date_str, str) or not date_str:
            return None
        normalized = date_str.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
        date_key = TypingHistoryGateway._extract_date_key(date_str)
        if date_key:
            try:
                return datetime.combine(date.fromisoformat(date_key), time.min)
            except ValueError:
                return None
        return None

    @staticmethod
    def _iso_week_key(day: date) -> str:
        iso = day.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"

    @staticmethod
    def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
        total = year * 12 + (month - 1) + offset
        return total // 12, total % 12 + 1
