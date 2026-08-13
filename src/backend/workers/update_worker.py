"""OTA 更新检查后台 Worker（ADR-014）。

在后台线程执行 ``UpdateChecker.check_for_update()``，避免阻塞 UI。
- 手动检查（``force=True``）：总是执行，错误抛给 UI。
- 自动检查（``force=False``）：受 ``check_interval_hours`` 节流，
  失败仅 log_warning，不抛给 UI（静默）。
- 节流时间戳存内存（类级共享，跨 worker 实例）；启动时内存为空，
  因此每次启动都会执行一次自动检查（满足"启动时检查一次"）。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from ..application.exception_handler import GlobalExceptionHandler
from ..utils.logger import log_info, log_warning
from .base_worker import BaseWorker

if TYPE_CHECKING:
    from ..integration.update_checker import UpdateInfo


class UpdateWorkerSignals(QObject):
    """UpdateWorker 专用信号。

    checkFinished(available, version, error_message)：检查完成。
    - 有新版：available=True，version=新版本号
    - 无新版：available=False，version=""，error=""
    - 失败：available=False，error=错误消息（自动检查时为空串，静默）
    """

    checkFinished = Signal(bool, str, str)
    finished = Signal()


class UpdateWorker(BaseWorker):
    """后台执行更新检查的 Worker。"""

    # 内存节流时间戳（monotonic 秒，类级共享，跨实例生效）。
    # 不持久化：每次启动从 0 开始，保证启动时自动检查一次。
    last_check_at = 0.0

    def __init__(
        self,
        update_checker,
        check_interval_hours: int = 24,
        force: bool = False,
    ) -> None:
        self._update_checker = update_checker
        self._check_interval_hours = max(int(check_interval_hours or 24), 1)
        self._force = force
        super().__init__(task=self._check, error_prefix="检查更新失败")
        # BaseWorker.__init__ 会覆盖 signals，必须在 super 之后重建
        self.signals = UpdateWorkerSignals()

    def run(self) -> None:
        """执行检查并发射 checkFinished。失败不经过 BaseWorker 的 failed 信号。"""
        try:
            info = self._task()
            if info is None:
                self.signals.checkFinished.emit(False, "", "")
            else:
                self.signals.checkFinished.emit(True, str(info.version), "")
        except Exception as e:
            msg = GlobalExceptionHandler.handle(e)
            log_warning(f"[UpdateWorker] 检查更新失败: {msg}")
            # 手动检查把错误抛给 UI；自动检查静默（error 传空串）
            self.signals.checkFinished.emit(False, "", msg if self._force else "")
        finally:
            self.signals.finished.emit()

    def _check(self) -> "UpdateInfo | None":
        """节流判定 + 调用 UpdateChecker。"""
        now = time.monotonic()
        if not self._force:
            elapsed = now - UpdateWorker.last_check_at
            if elapsed < self._check_interval_hours * 3600:
                log_info(
                    f"[UpdateWorker] 距上次检查不足 {self._check_interval_hours}h，"
                    "跳过自动检查"
                )
                return None
        UpdateWorker.last_check_at = now
        return self._update_checker.check_for_update()
