import sqlite3
from datetime import datetime
from pathlib import Path

from ..models.entity.char_stat import CharStat


class SqliteCharStatsRepository:
    """基于 SQLite 的字符统计持久化实现。"""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS char_stats (
        char              TEXT PRIMARY KEY,
        char_count        INTEGER NOT NULL DEFAULT 0,
        error_char_count  INTEGER NOT NULL DEFAULT 0,
        total_ms          REAL NOT NULL DEFAULT 0.0,
        min_ms            REAL NOT NULL DEFAULT 0.0,
        max_ms            REAL NOT NULL DEFAULT 0.0,
        last_seen         TEXT NOT NULL DEFAULT '',
        last_synced_at    TEXT,
        is_dirty          INTEGER NOT NULL DEFAULT 1
    );
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(self.CREATE_TABLE_SQL)

    def get(self, char: str) -> CharStat | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen "
                "FROM char_stats WHERE char = ?",
                (char,),
            ).fetchone()
        return self._row_to_stat(row) if row else None

    def get_batch(self, chars: list[str]) -> list[CharStat]:
        if not chars:
            return []
        placeholders = ",".join("?" for _ in chars)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen "
                f"FROM char_stats WHERE char IN ({placeholders})",
                chars,
            ).fetchall()
        return [self._row_to_stat(row) for row in rows]

    def get_chars_by_sort(
        self,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
        n: int = 10,
    ) -> list[CharStat]:
        if n <= 0:
            return []
        if sort_mode == "error_rate":
            order_by = "CAST(error_char_count AS REAL) / char_count DESC"
        elif sort_mode == "error_count":
            order_by = "error_char_count DESC"
        elif sort_mode == "weighted":
            w = weights or {}
            w_rate = float(w.get("error_rate", 0.6))
            w_total = float(w.get("total_count", 0.2))
            w_err = float(w.get("error_count", 0.2))
            order_by = (
                f"POWER(CAST(error_char_count AS REAL) / MAX(char_count, 1), {w_rate}) "
                f"* POWER(LOG(MAX(char_count, 1) + 1), {w_total}) "
                f"* POWER(LOG(MAX(error_char_count, 0) + 1), {w_err}) DESC"
            )
        else:
            order_by = "CAST(error_char_count AS REAL) / char_count DESC"

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen "
                f"FROM char_stats WHERE char_count > 0 ORDER BY {order_by} LIMIT ?",
                (n,),
            ).fetchall()
        return [self._row_to_stat(row) for row in rows]

    def get_weakest_chars(self, n: int) -> list[CharStat]:
        return self.get_chars_by_sort("error_rate", None, n)

    def save(self, stat: CharStat) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO char_stats (char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen, last_synced_at, is_dirty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 1) "
                "ON CONFLICT(char) DO UPDATE SET "
                "char_count = ?, error_char_count = ?, total_ms = ?, "
                "min_ms = ?, max_ms = ?, last_seen = ?, is_dirty = 1",
                (
                    stat.char,
                    stat.char_count,
                    stat.error_char_count,
                    stat.total_ms,
                    stat.min_ms,
                    stat.max_ms,
                    stat.last_seen or now,
                    stat.char_count,
                    stat.error_char_count,
                    stat.total_ms,
                    stat.min_ms,
                    stat.max_ms,
                    stat.last_seen or now,
                ),
            )

    def save_batch(self, stats: list[CharStat]) -> None:
        if not stats:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                "INSERT INTO char_stats (char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen, last_synced_at, is_dirty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 1) "
                "ON CONFLICT(char) DO UPDATE SET "
                "char_count = ?, error_char_count = ?, total_ms = ?, "
                "min_ms = ?, max_ms = ?, last_seen = ?, is_dirty = 1",
                [
                    (
                        s.char,
                        s.char_count,
                        s.error_char_count,
                        s.total_ms,
                        s.min_ms,
                        s.max_ms,
                        s.last_seen or now,
                        s.char_count,
                        s.error_char_count,
                        s.total_ms,
                        s.min_ms,
                        s.max_ms,
                        s.last_seen or now,
                    )
                    for s in stats
                ],
            )

    def get_all(self) -> list[CharStat]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen "
                "FROM char_stats"
            ).fetchall()
        return [self._row_to_stat(row) for row in rows]

    def get_all_dirty(self) -> list[CharStat]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen "
                "FROM char_stats WHERE is_dirty = 1"
            ).fetchall()
        return [self._row_to_stat(row) for row in rows]

    def mark_synced(self, chars: list[str], synced_at: str) -> None:
        if not chars:
            return
        placeholders = ",".join("?" for _ in chars)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"UPDATE char_stats SET is_dirty = 0, last_synced_at = ? WHERE char IN ({placeholders})",
                [synced_at, *chars],
            )

    @staticmethod
    def _row_to_stat(row: tuple) -> CharStat:
        return CharStat(
            char=row[0],
            char_count=row[1],
            error_char_count=row[2],
            total_ms=row[3],
            min_ms=row[4],
            max_ms=row[5],
            last_seen=row[6],
        )
