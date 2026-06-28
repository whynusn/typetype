"""AI 智能推荐 Qt 适配层。"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from ...application.usecases.generate_ai_text_usecase import (
        AiTextResult,
        GenerateAiTextUseCase,
    )


class AiTextAdapter(QObject):
    """AI 智能推荐 Qt 适配层。

    职责：
    - Qt 信号管理
    - Worker 异步执行（避免阻塞 UI）
    - 错误回传
    """

    textGenerated = Signal(str, str)  # (content, title)
    generationFailed = Signal(str)
    loadingChanged = Signal()

    def __init__(self, usecase: "GenerateAiTextUseCase") -> None:
        super().__init__()
        self._usecase = usecase
        self._loading = False
        self._thread_pool = QThreadPool.globalInstance()

    @property
    def loading(self) -> bool:
        return self._loading

    def _set_loading(self, loading: bool) -> None:
        if self._loading != loading:
            self._loading = loading
            self.loadingChanged.emit()

    @Slot()
    def requestAiText(self) -> None:
        """请求 AI 生成文本。走 Worker 避免阻塞 UI。"""
        if self._loading:
            return
        self._set_loading(True)
        worker = BaseWorker(
            task=self._usecase.execute,
            error_prefix="AI 生成文本失败",
        )
        worker.signals.succeeded.connect(self._on_success)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.finished.connect(lambda: self._set_loading(False))
        self._thread_pool.start(worker)

    def _on_success(self, result: "AiTextResult") -> None:
        if result.success:
            self.textGenerated.emit(result.text, result.title)
        else:
            self.generationFailed.emit(result.error_message)

    def _on_failed(self, msg: str) -> None:
        self.generationFailed.emit(msg)
