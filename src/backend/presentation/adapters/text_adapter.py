from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...application.gateways.text_gateway import TextGateway
from ...application.usecases.load_text_usecase import LoadTextUseCase
from ...models.config.text_source_config import TextSourceEntry
from ...workers.text_load_worker import TextLoadWorker


class TextAdapter(QObject):
    """文本加载 Qt 适配层。"""

    # 信号定义
    textLoaded = Signal(str)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()

    def __init__(
        self,
        text_gateway: TextGateway,
        load_text_usecase: LoadTextUseCase,
    ):
        super().__init__()
        self._text_gateway = text_gateway
        self._load_text_usecase = load_text_usecase
        self._text_loading = False
        self._thread_pool = QThreadPool.globalInstance()

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def _on_text_loaded(self, text: object) -> None:
        if text is None:
            self.textLoadFailed.emit("加载文本失败：未获取到文本")
            return
        if not isinstance(text, str):
            self.textLoadFailed.emit("加载文本失败：返回数据格式错误")
            return
        self.textLoaded.emit(text)

    def _on_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    def _on_text_load_finished(self) -> None:
        self._set_text_loading(False)

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        if self._text_loading:
            return

        source = self._text_gateway.get_source(source_key)
        if not source:
            self.textLoadFailed.emit(f"加载文本失败：未知载文来源({source_key})")
            return

        if source.local_path:
            self._load_local(source)
        else:
            self._load_network(source)

    def _load_local(self, source: TextSourceEntry) -> None:
        self._set_text_loading(True)
        try:
            result = self._load_text_usecase.load_from_source(source)
            if result.success:
                self._on_text_loaded(result.text)
            else:
                self._on_text_load_failed(f"加载文本失败：{result.error_message}")
        except Exception as e:
            self._on_text_load_failed(
                f"加载文本失败：{GlobalExceptionHandler.handle(e)}"
            )
        finally:
            self._set_text_loading(False)

    def _load_network(self, source: TextSourceEntry) -> None:
        self._set_text_loading(True)
        worker = TextLoadWorker(
            load_text_usecase=self._load_text_usecase,
            source=source,
        )
        worker.signals.succeeded.connect(self._on_text_loaded)
        worker.signals.failed.connect(self._on_text_load_failed)
        worker.signals.finished.connect(self._on_text_load_finished)
        self._thread_pool.start(worker)

    @Slot()
    def loadTextFromClipboard(self) -> None:
        """从剪贴板加载文本。"""
        if self._text_loading:
            return

        self._set_text_loading(True)
        try:
            result = self._load_text_usecase.load_from_clipboard()
            if result.success:
                self._on_text_loaded(result.text)
            else:
                self._on_text_load_failed(f"加载文本失败：{result.error_message}")
        except Exception as e:
            self._on_text_load_failed(
                f"加载文本失败：{GlobalExceptionHandler.handle(e)}"
            )
        finally:
            self._set_text_loading(False)

    @property
    def text_loading(self) -> bool:
        return self._text_loading

    def get_source_options(self) -> list[dict[str, str]]:
        """获取 UI 可选的来源列表。"""
        return self._text_gateway.get_source_options()

    def get_default_source_key(self) -> str:
        return self._text_gateway.get_default_source_key()
