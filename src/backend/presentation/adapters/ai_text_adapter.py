"""AI 智能推荐 Qt 适配层。"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from ...application.usecases.generate_ai_text_usecase import (
        AiTextResult,
        GenerateAiTextUseCase,
    )
    from ...config.runtime_config import RuntimeConfig
    from ...integration.secure_token_store import SecureTokenStore


class AiTextAdapter(QObject):
    """AI 智能推荐 Qt 适配层。

    职责：
    - Qt 信号管理
    - Worker 异步执行（避免阻塞 UI）
    - 错误回传
    - 配置管理（provider/model/api_key）
    """

    AI_API_KEY = "ai_api_key"

    textGenerated = Signal(str, str)  # (content, title)
    generationFailed = Signal(str)
    loadingChanged = Signal()
    configChanged = Signal()

    def __init__(
        self,
        usecase: "GenerateAiTextUseCase",
        runtime_config: "RuntimeConfig",
        token_store: "SecureTokenStore",
    ) -> None:
        super().__init__()
        self._usecase = usecase
        self._runtime_config = runtime_config
        self._token_store = token_store
        self._loading = False
        self._thread_pool = QThreadPool.globalInstance()

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def provider(self) -> str:
        return self._runtime_config.ai.provider

    @property
    def base_url(self) -> str:
        return self._runtime_config.ai.base_url

    @property
    def model(self) -> str:
        return self._runtime_config.ai.model

    @property
    def max_chars(self) -> int:
        return self._runtime_config.ai.max_chars

    @property
    def has_api_key(self) -> bool:
        return bool(self._token_store.get_token(self.AI_API_KEY))

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

    @Slot(str, result=bool)
    def updateApiKey(self, api_key: str) -> bool:
        """保存 API Key 到 keyring。"""
        try:
            self._token_store.save_token(self.AI_API_KEY, api_key)
            return True
        except Exception:
            return False

    @Slot(str)
    def updateProvider(self, provider: str) -> None:
        """更新 AI provider 并持久化。"""
        self._runtime_config.update_ai_config(provider=provider)
        self.configChanged.emit()

    @Slot(str)
    def updateBaseUrl(self, base_url: str) -> None:
        """更新 AI base_url 并持久化。"""
        self._runtime_config.update_ai_config(base_url=base_url)
        self.configChanged.emit()

    @Slot(str)
    def updateModel(self, model: str) -> None:
        """更新 AI model 并持久化。"""
        self._runtime_config.update_ai_config(model=model)
        self.configChanged.emit()

    @Slot(int)
    def updateMaxChars(self, max_chars: int) -> None:
        """更新生成文本目标字数并持久化。"""
        self._runtime_config.update_ai_config(max_chars=max_chars)
        self.configChanged.emit()
