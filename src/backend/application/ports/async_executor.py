"""异步执行器协议。"""

from collections.abc import Callable
from typing import Protocol


class AsyncExecutor(Protocol):
    """异步执行器协议，用于 Domain Service 提交异步任务。

    实现示例：
    - QtAsyncExecutor: 使用 QThreadPool
    - ThreadPoolAsyncExecutor: 使用标准库 ThreadPoolExecutor
    """

    def submit(self, task: Callable[[], None]) -> None:
        """提交异步任务。"""
        ...
