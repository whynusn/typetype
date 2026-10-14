from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from ..application.exception_handler import GlobalExceptionHandler


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class BaseWorker(QRunnable):
    def __init__(self, task: Callable[[], Any], error_prefix: str = "任务执行失败"):
        super().__init__()
        # QThreadPool 的自动销毁可能早于 queued signal 的处理，导致
        # WorkerSignals 被删除后 succeeded/finished 信号随机丢失。
        # 提交方必须继续持有 worker；这里先关闭危险的默认行为。
        self.setAutoDelete(False)
        self._task = task
        self._error_prefix = error_prefix
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._task()
            self.signals.succeeded.emit(result)
        except Exception as e:
            msg = GlobalExceptionHandler.handle(e)
            self.signals.failed.emit(f"{self._error_prefix}：{msg}")
        finally:
            self.signals.finished.emit()


class WorkerReleaseProxy(QObject):
    """在 Worker 完成后，以稳定的 QObject 接收者释放 owner 的引用。"""

    def __init__(
        self,
        owner: QObject,
        worker: QRunnable,
        release: Callable[[QRunnable], None],
    ) -> None:
        super().__init__(owner)
        self._worker = worker
        self._release = release

    @Slot()
    def release(self) -> None:
        worker = self._worker
        self._release(worker)
        self.deleteLater()


class _WorkerReleaseProxy(QObject):
    """把无 owner worker 的释放动作绑定到一个稳定的 QObject 接收者。"""

    def __init__(self, manager: "_WorkerLifetimeManager", worker: QRunnable):
        super().__init__(manager)
        self._manager = manager
        self._worker = worker

    @Slot()
    def release(self) -> None:
        worker = self._worker
        self._manager.defer_release(worker)
        self.deleteLater()


class _WorkerLifetimeManager(QObject):
    """在主线程延迟释放无 owner worker 的 Python wrapper。

    ``finished`` 的裸 Python 回调会在发射线程直接执行。若它释放了
    worker 的最后一个引用，仍排队在主线程的 ``succeeded``/``failed``
    回调会看到已销毁的 ``WorkerSignals``。使用 QObject proxy 作为接收者，
    让 Qt 的 AutoConnection 在真实线程间排队、在同步测试中直接执行。
    """

    def __init__(self) -> None:
        super().__init__()
        self._workers_by_id: dict[int, QRunnable] = {}
        self._proxies_by_id: dict[int, _WorkerReleaseProxy] = {}
        self._pending_releases: dict[int, QRunnable] = {}

    def retain(self, worker: QRunnable) -> None:
        self._workers_by_id[id(worker)] = worker
        proxy = _WorkerReleaseProxy(self, worker)
        self._proxies_by_id[id(worker)] = proxy
        worker.signals.finished.connect(proxy.release)

    @Slot(object)
    def defer_release(self, worker: QRunnable) -> None:
        """等当前事件队列清空后再释放最后一个 Worker 引用。

        ``succeeded``/``failed`` 与 ``finished`` 都可能以 queued event
        进入主线程。即使连接顺序通常稳定，也不能让 finished 的释放动作
        抢在其他业务信号之前销毁 ``WorkerSignals``。
        """
        worker_id = id(worker)
        self._pending_releases[worker_id] = worker
        QTimer.singleShot(
            0,
            lambda worker_id=worker_id: self.release_pending(worker_id),
        )

    @Slot(int)
    def release_pending(self, worker_id: int) -> None:
        worker = self._pending_releases.pop(worker_id, None)
        if worker is not None:
            self.release_from_main_thread(worker)

    @Slot(object)
    def release_from_main_thread(self, worker: QRunnable) -> None:
        self._workers_by_id.pop(id(worker), None)
        self._proxies_by_id.pop(id(worker), None)


_LIFETIME_MANAGER: _WorkerLifetimeManager | None = None


def _worker_lifetime_manager() -> _WorkerLifetimeManager:
    global _LIFETIME_MANAGER
    if _LIFETIME_MANAGER is None:
        _LIFETIME_MANAGER = _WorkerLifetimeManager()
    return _LIFETIME_MANAGER


def retain_worker(worker: QRunnable) -> None:
    """独立于 Adapter 生命周期保活 worker，直到完成信号处理完毕。

    Adapter 自身仍可持有 worker 以维护业务状态，但 QObject owner 可能在
    worker 完成前销毁。全局 manager 是最后一道 Python 引用，避免
    ``WorkerSignals`` 在 queued signal 交付前被回收。
    """
    _worker_lifetime_manager().retain(worker)


def start_worker(thread_pool: QThreadPool, worker: QRunnable) -> None:
    """提交带 Qt 信号的 worker，并保活至主线程处理完 ``finished``。

    Adapter 通常会把 worker 放入自己的活动集合；对没有自然 owner 的
    一次性后台操作（例如 Bridge 的通用提交器）使用此函数，避免 Python
    wrapper 在 QThreadPool 排队期间被回收。真正的释放槽使用 queued
    connection，避免早于业务 queued 信号释放 wrapper。
    """
    worker.setAutoDelete(False)
    retain_worker(worker)
    thread_pool.start(worker)
