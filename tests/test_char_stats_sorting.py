import pytest

from src.backend.integration.sqlite_char_stats_repository import (
    SqliteCharStatsRepository,
)
from src.backend.models.entity.char_stat import CharStat


@pytest.fixture
def populated_repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    repo = SqliteCharStatsRepository(db_path)
    repo.init_db()
    test_data = [
        # (char, char_count, error_char_count, total_ms)
        ("A", 100, 50, 10000.0),  # 50% error rate
        ("B", 1000, 10, 50000.0),  # 1% error rate
        ("C", 10, 10, 5000.0),  # 100% error rate
        ("D", 500, 100, 30000.0),  # 20% error rate
        ("E", 5, 1, 2000.0),  # 20% error rate
    ]
    for char, cc, ecc, tms in test_data:
        repo.save(
            CharStat(
                char=char,
                char_count=cc,
                error_char_count=ecc,
                total_ms=tms,
                min_ms=1.0,
                max_ms=100.0,
                last_seen="2026-01-01",
            )
        )
    return repo


class TestSortByErrorRate:
    def test_order(self, populated_repo):
        result = populated_repo.get_chars_by_sort("error_rate", n=10)
        chars = [s.char for s in result]
        # C(100%) > A(50%) > D(20%) > E(20%) > B(1%)
        assert chars[0] == "C"
        assert chars[1] == "A"
        # D and E both 20% error rate — D appears first due to higher char_count in stable sort
        assert chars[2] == "D"
        assert chars[3] == "E"
        assert chars[4] == "B"

    def test_error_rates(self, populated_repo):
        result = populated_repo.get_chars_by_sort("error_rate", n=10)
        rates = {s.char: s.error_rate for s in result}
        assert rates["C"] == pytest.approx(100.0)
        assert rates["A"] == pytest.approx(50.0)
        assert rates["D"] == pytest.approx(20.0)
        assert rates["E"] == pytest.approx(20.0)
        assert rates["B"] == pytest.approx(1.0)


class TestSortByErrorCount:
    def test_order(self, populated_repo):
        result = populated_repo.get_chars_by_sort("error_count", n=10)
        chars = [s.char for s in result]
        # D(100) > A(50) > B(10) >= C(10) > E(1)
        assert chars[0] == "D"
        assert chars[1] == "A"
        assert chars[4] == "E"

    def test_error_counts(self, populated_repo):
        result = populated_repo.get_chars_by_sort("error_count", n=10)
        counts = {s.char: s.error_char_count for s in result}
        assert counts["D"] == 100
        assert counts["A"] == 50
        assert counts["B"] == 10
        assert counts["C"] == 10
        assert counts["E"] == 1


class TestSortByWeighted:
    def test_returns_results(self, populated_repo):
        result = populated_repo.get_chars_by_sort("weighted", n=10)
        assert len(result) == 5
        chars = [s.char for s in result]
        # B has highest total_count but low error — C has highest error rate
        # weighted should favor high error_rate (weight 0.6 default)
        assert chars[0] == "C"

    def test_deterministic(self, populated_repo):
        r1 = populated_repo.get_chars_by_sort("weighted", n=10)
        r2 = populated_repo.get_chars_by_sort("weighted", n=10)
        assert [s.char for s in r1] == [s.char for s in r2]

    def test_custom_weights(self, populated_repo):
        # Custom weights: favor error_count heavily
        result = populated_repo.get_chars_by_sort(
            "weighted",
            weights={"error_rate": 0.1, "total_count": 0.1, "error_count": 0.8},
            n=10,
        )
        assert len(result) == 5
        # D has highest error_count (100), should rank high
        chars = [s.char for s in result]
        assert chars[0] == "D"


class TestWeakestCharsBackwardCompat:
    def test_matches_error_rate(self, populated_repo):
        weakest = populated_repo.get_weakest_chars(3)
        by_rate = populated_repo.get_chars_by_sort("error_rate", n=3)
        assert [s.char for s in weakest] == [s.char for s in by_rate]


class TestEmptyDb:
    def test_empty_returns_empty(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        repo = SqliteCharStatsRepository(db_path)
        repo.init_db()
        assert repo.get_chars_by_sort("error_rate", n=10) == []
        assert repo.get_chars_by_sort("error_count", n=10) == []
        assert repo.get_chars_by_sort("weighted", n=10) == []

    def test_zero_n_returns_empty(self, populated_repo):
        assert populated_repo.get_chars_by_sort("error_rate", n=0) == []
