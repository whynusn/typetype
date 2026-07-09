from datetime import date

from src.backend.application.gateways.typing_history_gateway import TypingHistoryGateway


class InMemoryTypingHistoryStore:
    def __init__(self, records=None):
        self.data = {"version": 1, "records": records or []}

    def load(self):
        return {
            "version": self.data.get("version", 1),
            "records": list(self.data.get("records", [])),
        }

    def save(self, data):
        self.data = data


def _record(date_text: str, chars: int):
    return {"date": date_text, "charNum": chars}


def test_hourly_trend_aggregates_recent_24_hours_by_hour():
    gateway = TypingHistoryGateway(
        InMemoryTypingHistoryStore(
            [
                _record("2026-07-09 10:15:00", 20),
                _record("2026-07-09 10:55:00", 5),
                _record("2026-07-09T23:00:00", 7),
                _record("2026-07-08 10:00:00", 99),
            ]
        ),
        today_provider=lambda: date(2026, 7, 9),
    )

    trend = gateway.get_trend("hour")

    assert len(trend) == 24
    assert trend[10] == {"date": "2026-07-09 10:00", "period": "hour", "chars": 25}
    assert trend[23] == {"date": "2026-07-09 23:00", "period": "hour", "chars": 7}


def test_daily_trend_keeps_recent_30_days_by_day():
    gateway = TypingHistoryGateway(
        InMemoryTypingHistoryStore(
            [
                _record("2026-07-08 10:00:00", 20),
                _record("2026-07-09 10:00:00", 7),
            ]
        ),
        today_provider=lambda: date(2026, 7, 9),
    )

    trend = gateway.get_trend("day")

    assert len(trend) == 30
    assert trend[-2] == {"date": "2026-07-08", "period": "day", "chars": 20}
    assert trend[-1] == {"date": "2026-07-09", "period": "day", "chars": 7}


def test_weekly_trend_aggregates_recent_12_iso_weeks():
    gateway = TypingHistoryGateway(
        InMemoryTypingHistoryStore(
            [
                _record("2026-07-06 10:00:00", 20),
                _record("2026-07-09 10:00:00", 7),
                _record("2026-06-29 09:00:00", 3),
            ]
        ),
        today_provider=lambda: date(2026, 7, 9),
    )

    trend = gateway.get_trend("week")

    assert len(trend) == 12
    assert trend[-2] == {"date": "2026-W27", "period": "week", "chars": 3}
    assert trend[-1] == {"date": "2026-W28", "period": "week", "chars": 27}


def test_monthly_trend_aggregates_recent_12_months():
    gateway = TypingHistoryGateway(
        InMemoryTypingHistoryStore(
            [
                _record("2026-07-09 10:00:00", 20),
                _record("2026-07-01 10:00:00", 7),
                _record("2026-06-30 09:00:00", 3),
            ]
        ),
        today_provider=lambda: date(2026, 7, 9),
    )

    trend = gateway.get_trend("month")

    assert len(trend) == 12
    assert trend[-2] == {"date": "2026-06", "period": "month", "chars": 3}
    assert trend[-1] == {"date": "2026-07", "period": "month", "chars": 27}
