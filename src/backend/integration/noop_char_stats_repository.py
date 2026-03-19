from ..models.char_stats import CharStat


class NoopCharStatsRepository:
    """占位实现，无持久化时不影响打字功能。"""

    def init_db(self) -> None:
        pass

    def get(self, char: str) -> CharStat | None:
        return None

    def get_batch(self, chars: list[str]) -> list[CharStat]:
        return []

    def save(self, stat: CharStat) -> None:
        pass

    def save_batch(self, stats: list[CharStat]) -> None:
        pass

    def get_all(self) -> list[CharStat]:
        return []

    def get_all_dirty(self) -> list[CharStat]:
        return []

    def mark_synced(self, chars: list[str], synced_at: str) -> None:
        pass
