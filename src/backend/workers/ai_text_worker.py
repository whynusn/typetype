"""AI 文本生成流式 Worker。"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ..application.exception_handler import GlobalExceptionHandler
from ..application.usecases.generate_ai_text_usecase import AiTextResult


class AiTextWorkerSignals(QObject):
    chunk = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class AiTextWorker(QRunnable):
    """流式 AI 文本生成 Worker。

    与 BaseWorker 的区别：增加了 chunk 信号，每收到一块文本时发射。
    """

    def __init__(
        self,
        task: Callable[[Callable[[str], None]], AiTextResult],
        error_prefix: str = "AI 生成文本失败",
    ):
        super().__init__()
        self._task = task
        self._error_prefix = error_prefix
        self.signals = AiTextWorkerSignals()

    def _on_chunk(self, chunk: str) -> None:
        self.signals.chunk.emit(chunk)

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(self._on_chunk)
            self.signals.succeeded.emit(result)
        except Exception as e:
            msg = GlobalExceptionHandler.handle(e)
            self.signals.failed.emit(f"{self._error_prefix}：{msg}")
        finally:
            self.signals.finished.emit()
