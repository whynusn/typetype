"""Qt 异步执行器实现。"""

from collections.abc import Callable

from PySide6.QtCore import QRunnable, QThreadPool


class QtAsyncExecutor:
    """基于 QThreadPool 的异步执行器。"""

    def __init__(self):
        self._thread_pool = QThreadPool.globalInstance()

    def submit(self, task: Callable[[], None]) -> None:
        """提交异步任务到 QThreadPool。"""
        runnable = _TaskRunnable(task)
        self._thread_pool.start(runnable)


class _TaskRunnable(QRunnable):
    """将 Callable 包装为 QRunnable。"""

    def __init__(self, task: Callable[[], None]):
        super().__init__()
        self._task = task
        self.setAutoDelete(True)

    def run(self) -> None:
        self._task()
