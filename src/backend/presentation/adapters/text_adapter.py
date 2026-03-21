"""文本加载 Qt 适配层。

负责：
- Qt 信号发射
- 异步任务管理（QThreadPool）

不负责：
- 路由逻辑（由 LoadTextUseCase 负责）
- 文本加载逻辑（由 TextGateway 负责）
- 异常处理（由 LoadTextUseCase 负责）
"""

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.gateways.text_gateway import TextGateway
from ...application.usecases.load_text_usecase import LoadTextUseCase
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
        """请求加载文本。"""
        if self._text_loading:
            return

        source = self._text_gateway.get_source(source_key)
        if not source:
            self.textLoadFailed.emit(f"加载文本失败：未知载文来源({source_key})")
            return

        if source.type == "local":
            self._request_load_from_local(source_key)
        elif source.type in ("network_direct", "network_catalog"):
            self._request_load_from_network(source_key)
        else:
            self.textLoadFailed.emit(f"加载文本失败：未知载文来源类型({source_key})")

    def _request_load_from_network(self, source_key: str) -> None:
        """异步从网络加载文本。"""
        self._set_text_loading(True)
        worker = TextLoadWorker(
            load_text_usecase=self._load_text_usecase,
            source_key=source_key,
        )
        worker.signals.succeeded.connect(self._on_text_loaded)
        worker.signals.failed.connect(self._on_text_load_failed)
        worker.signals.finished.connect(self._on_text_load_finished)
        self._thread_pool.start(worker)

    def _request_load_from_local(self, source_key: str) -> None:
        """从本地加载文本。"""
        self._set_text_loading(True)
        try:
            result = self._load_text_usecase.load(source_key)
            if result.success:
                self._on_text_loaded(result.text)
            else:
                self._on_text_load_failed(f"加载文本失败：{result.error_message}")
        except Exception as e:
            self._on_text_load_failed(f"加载文本失败：{str(e)}")
        finally:
            self._set_text_loading(False)

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
            self._on_text_load_failed(f"加载文本失败：{str(e)}")
        finally:
            self._set_text_loading(False)

    @property
    def text_loading(self) -> bool:
        return self._text_loading

    def get_source_options(self) -> list[dict[str, str]]:
        """获取 UI 可选的来源列表。"""
        return self._text_gateway.get_source_options()

    def get_default_source_key(self) -> str:
        """获取默认来源 key。"""
        return self._text_gateway.get_default_source_key()
