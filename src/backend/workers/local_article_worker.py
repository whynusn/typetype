from collections.abc import Callable
from typing import Any

from .base_worker import BaseWorker


class LocalArticleWorker(BaseWorker):
    """本地长文 Worker - 在后台线程执行文件 I/O。"""

    def __init__(self, task: Callable[[], Any], error_prefix: str):
        super().__init__(task=task, error_prefix=error_prefix)
