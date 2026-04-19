from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...domain.services.char_stats_service import CharStatsService
from ...utils.logger import log_info
from ...workers.weak_chars_query_worker import WeakCharsQueryWorker


class CharStatsAdapter(QObject):
    weakestCharsLoaded = Signal(list)

    def __init__(self, char_stats_service: CharStatsService | None = None):
        super().__init__()
        self._char_stats_service = char_stats_service

    def _on_weak_chars_loaded(self, data: list[dict[str, Any]]) -> None:
        self.weakestCharsLoaded.emit(data)

    @Slot()
    def loadWeakChars(
        self,
        n: int = 10,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
    ) -> None:
        if not self._char_stats_service:
            self.weakestCharsLoaded.emit([])
            return
        worker = WeakCharsQueryWorker(
            self._char_stats_service,
            n=n,
            sort_mode=sort_mode,
            weights=weights,
        )
        worker.signals.succeeded.connect(self._on_weak_chars_loaded)
        worker.signals.failed.connect(lambda msg: log_info(f"[CharStatsAdapter] {msg}"))
        QThreadPool.globalInstance().start(worker)
