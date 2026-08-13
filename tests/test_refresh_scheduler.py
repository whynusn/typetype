"""RefreshScheduler：轻量常驻调度（非 Qt 环境降级同步）。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.backend.integration.refresh_scheduler import RefreshScheduler


def test_tick_forwards_to_service() -> None:
    service = MagicMock()
    scheduler = RefreshScheduler(service)
    scheduler.tick()
    service.scheduled_tick.assert_called_once()


def test_start_stop_without_qt_event_loop(tmp_path) -> None:
    # 无 QApplication 环境：start() 不崩溃（内部 QTimer 单次创建容错），stop() 幂等
    service = MagicMock()
    scheduler = RefreshScheduler(service)
    scheduler.start()
    scheduler.stop()
    scheduler.stop()  # 幂等
