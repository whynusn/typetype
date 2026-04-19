from ..models.entity.char_stat import CharStat


class NoopCharStatsRepository:
    """占位实现，无持久化时不影响打字功能。"""

    def init_db(self) -> None:
        pass

    def get(self, char: str) -> CharStat | None:
        return None

    def get_batch(self, chars: list[str]) -> list[CharStat]:
        return []

    def get_chars_by_sort(
        self,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
        n: int = 10,
    ) -> list[CharStat]:
        return []

    def get_weakest_chars(self, n: int) -> list[CharStat]:
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
