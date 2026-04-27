from typing import Any

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from ...domain.services.char_stats_service import CharStatsService
from ...utils.logger import log_info
from ...workers.weak_chars_query_worker import WeakCharsQueryWorker


class CharStatsAdapter(QObject):
    weakestCharsLoaded = Signal(list)

    def __init__(self, char_stats_service: CharStatsService | None = None):
        super().__init__()
        self._char_stats_service = char_stats_service
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(150)
        self._debounce_timer.timeout.connect(self._dispatch_weak_chars_query)
        self._pending_args: tuple[int, str, dict | None] | None = None
        self._latest_requested: (
            tuple[int, str, tuple[tuple[str, float], ...] | None] | None
        ) = None
        self._inflight = False
        self._rerun_after_inflight = False

    def _normalized_weights(
        self, weights: dict | None
    ) -> tuple[tuple[str, float], ...] | None:
        if not weights:
            return None
        normalized: list[tuple[str, float]] = []
        for key in sorted(weights.keys()):
            try:
                normalized.append((key, float(weights[key])))
            except Exception:
                continue
        return tuple(normalized)

    def _on_weak_chars_loaded(
        self,
        data: list[dict[str, Any]],
        signature: tuple[int, str, tuple[tuple[str, float], ...] | None],
    ) -> None:
        self._inflight = False
        if signature == self._latest_requested:
            self.weakestCharsLoaded.emit(data)
        if self._rerun_after_inflight:
            self._rerun_after_inflight = False
            self._dispatch_weak_chars_query()

    def _on_weak_chars_failed(
        self,
        message: str,
        signature: tuple[int, str, tuple[tuple[str, float], ...] | None],
    ) -> None:
        self._inflight = False
        if signature == self._latest_requested:
            log_info(f"[CharStatsAdapter] {message}")
        if self._rerun_after_inflight:
            self._rerun_after_inflight = False
            self._dispatch_weak_chars_query()

    def _dispatch_weak_chars_query(self) -> None:
        if not self._char_stats_service or self._pending_args is None:
            return
        if self._inflight:
            self._rerun_after_inflight = True
            return

        n, sort_mode, weights = self._pending_args
        signature = (n, sort_mode, self._normalized_weights(weights))
        if signature != self._latest_requested:
            return

        self._inflight = True
        worker = WeakCharsQueryWorker(
            self._char_stats_service,
            n=n,
            sort_mode=sort_mode,
            weights=weights,
        )
        worker.signals.succeeded.connect(
            lambda data, sig=signature: self._on_weak_chars_loaded(data, sig)
        )
        worker.signals.failed.connect(
            lambda msg, sig=signature: self._on_weak_chars_failed(msg, sig)
        )
        QThreadPool.globalInstance().start(worker)

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

        normalized = self._normalized_weights(weights)
        signature = (n, sort_mode, normalized)
        if signature == self._latest_requested and self._debounce_timer.isActive():
            return

        self._pending_args = (n, sort_mode, weights)
        self._latest_requested = signature
        self._debounce_timer.start()
