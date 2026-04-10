"""排行榜适配层 - Qt 信号管理。"""

from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...integration.leaderboard_fetcher import LeaderboardFetcher
from ...workers.leaderboard_worker import LeaderboardWorker


class LeaderboardAdapter(QObject):
    """排行榜 Qt 适配层。

    职责：
    - Qt 信号管理
    - 线程协调（异步加载排行榜）
    - 错误回传
    """

    # 信号定义
    leaderboardLoaded = Signal(dict)  # 包含 text_info, leaderboard, total
    leaderboardLoadFailed = Signal(str)
    leaderboardLoadingChanged = Signal()

    def __init__(self, leaderboard_fetcher: LeaderboardFetcher):
        super().__init__()
        self._leaderboard_fetcher = leaderboard_fetcher
        self._thread_pool = QThreadPool.globalInstance()
        self._loading = False

    def _set_loading(self, loading: bool) -> None:
        if self._loading != loading:
            self._loading = loading
            self.leaderboardLoadingChanged.emit()

    def _on_leaderboard_loaded(self, data: dict[str, Any]) -> None:
        """处理排行榜加载成功。"""
        self.leaderboardLoaded.emit(data)

    def _on_leaderboard_load_failed(self, message: str) -> None:
        """处理排行榜加载失败。"""
        self.leaderboardLoadFailed.emit(message)

    def _on_leaderboard_load_finished(self) -> None:
        """处理排行榜加载完成。"""
        self._set_loading(False)

    @Slot(str)
    def loadLeaderboard(self, source_key: str) -> None:
        """加载指定来源的排行榜。

        Args:
            source_key: 文本来源标识，如 "jisubei"
        """
        if self._loading:
            return

        self._set_loading(True)
        worker = LeaderboardWorker(
            leaderboard_fetcher=self._leaderboard_fetcher,
            source_key=source_key,
        )
        worker.signals.succeeded.connect(self._on_leaderboard_loaded)
        worker.signals.failed.connect(self._on_leaderboard_load_failed)
        worker.signals.finished.connect(self._on_leaderboard_load_finished)
        self._thread_pool.start(worker)

    @property
    def loading(self) -> bool:
        return self._loading
