from collections.abc import Callable
from typing import Any

from .base_worker import BaseWorker


class TrainerWorker(BaseWorker):
    """练单器后台任务 Worker。"""

    def __init__(self, task: Callable[[], Any], error_prefix: str):
        super().__init__(task=task, error_prefix=error_prefix)
