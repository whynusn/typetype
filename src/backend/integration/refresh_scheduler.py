"""常驻轻量调度：周期扫描 interval 到期快照，后台刷新。

非 Qt 事件循环环境（测试/CLI）start() 容错降级为无操作；tick() 恒可调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logger import log_warning

if TYPE_CHECKING:
    from ..application.services.snapshot_catalog_service import SnapshotCatalogService


class RefreshScheduler:
    def __init__(
        self, service: "SnapshotCatalogService", interval_ms: int = 60_000
    ) -> None:
        self._service = service
        self._interval_ms = max(1000, interval_ms)
        self._timer = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            from PySide6.QtCore import QTimer

            self._timer = QTimer()
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self.tick)
            self._timer.start()
        except Exception as e:
            # 无 Qt 事件循环：降级为手动 tick（不崩溃）
            log_warning(f"[RefreshScheduler] Qt 定时器不可用，降级手动刷新: {e}")
            self._timer = None

    def stop(self) -> None:
        self._running = False
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
        except Exception:
            self._timer = None

    def tick(self) -> None:
        """单次到期扫描（测试/手动/定时器共用入口）。"""
        try:
            self._service.scheduled_tick()
        except Exception as e:
            log_warning(f"[RefreshScheduler] tick 失败: {e}")
