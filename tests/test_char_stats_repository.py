import sqlite3
import tempfile
from pathlib import Path

from src.backend.integration.sqlite_char_stats_repository import (
    SqliteCharStatsRepository,
)
from src.backend.integration.noop_char_stats_repository import (
    NoopCharStatsRepository,
)
from src.backend.models.entity.char_stat import CharStat


class TestSqliteCharStatsRepository:
    def _create_repo(self):
        path = tempfile.mktemp(suffix=".db")
        repo = SqliteCharStatsRepository(db_path=path)
        repo.init_db()
        return repo, path

    def test_init_db_creates_table(self):
        path = tempfile.mktemp(suffix=".db")
        repo = SqliteCharStatsRepository(db_path=path)
        repo.init_db()
        assert Path(path).exists()
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='char_stats'"
            ).fetchone()
            assert row is not None

    def test_save_and_get(self):
        repo, path = self._create_repo()
        stat = CharStat(
            char="测",
            char_count=5,
            error_char_count=1,
            total_ms=500.0,
            min_ms=80.0,
            max_ms=120.0,
            last_seen="2026-01-01 00:00:00",
        )
        repo.save(stat)
        loaded = repo.get("测")
        assert loaded is not None
        assert loaded.char == "测"
        assert loaded.char_count == 5
        assert loaded.error_char_count == 1
        assert loaded.total_ms == 500.0

    def test_save_upsert(self):
        repo, path = self._create_repo()
        repo.save(CharStat(char="A", char_count=3, error_char_count=1))
        repo.save(CharStat(char="A", char_count=8, error_char_count=2))
        loaded = repo.get("A")
        assert loaded.char_count == 8
        assert loaded.error_char_count == 2

    def test_save_batch(self):
        repo, path = self._create_repo()
        stats = [
            CharStat(char="A", char_count=1, error_char_count=0),
            CharStat(char="B", char_count=2, error_char_count=1),
            CharStat(char="C", char_count=3, error_char_count=0),
        ]
        repo.save_batch(stats)
        all_stats = repo.get_all()
        assert len(all_stats) == 3

    def test_get_all_empty(self):
        repo, path = self._create_repo()
        assert repo.get_all() == []

    def test_get_all_dirty(self):
        repo, path = self._create_repo()
        repo.save(CharStat(char="A", char_count=1))
        repo.save(CharStat(char="B", char_count=2))
        dirty = repo.get_all_dirty()
        assert len(dirty) == 2

    def test_mark_synced(self):
        repo, path = self._create_repo()
        repo.save(CharStat(char="A", char_count=1))
        repo.save(CharStat(char="B", char_count=2))
        repo.mark_synced(["A"], "2026-03-19 12:00:00")
        dirty = repo.get_all_dirty()
        assert len(dirty) == 1
        assert dirty[0].char == "B"

    def test_get_nonexistent(self):
        repo, path = self._create_repo()
        assert repo.get("Z") is None


class TestNoopCharStatsRepository:
    def test_all_noop(self):
        repo = NoopCharStatsRepository()
        repo.init_db()
        assert repo.get("A") is None
        repo.save(CharStat(char="A", char_count=1))
        assert repo.get_all() == []
        assert repo.get_all_dirty() == []
        repo.mark_synced(["A"], "2026-03-19 12:00:00")
