from collections.abc import Callable
from typing import Any

from .base_worker import BaseWorker


class WenlaiWorker(BaseWorker):
    """晴发文后台任务 Worker。"""

    def __init__(self, task: Callable[[], Any], error_prefix: str = "晴发文操作失败"):
        super().__init__(task=task, error_prefix=error_prefix)
