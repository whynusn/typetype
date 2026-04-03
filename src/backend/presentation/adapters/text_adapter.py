from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...application.usecases.load_text_usecase import LoadTextUseCase
from ...config.runtime_config import RuntimeConfig
from ...workers.text_load_worker import TextLoadWorker


class TextAdapter(QObject):
    """文本加载 Qt 适配层。

    职责：
    - Qt 信号管理
    - 线程协调（本地同步、网络异步）
    - 错误回传
    - UI 配置展示（来源选项、默认来源）

    不负责：
    - 业务路由决策（由 LoadTextUseCase + TextSourceGateway 负责）
    """

    # 信号定义
    textLoaded = Signal(str)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        load_text_usecase: LoadTextUseCase,
    ):
        super().__init__()
        self._runtime_config = runtime_config
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
        """请求加载文本。

        Presentation 仅执行 Application 给出的加载计划：
        - sync: 同步调用
        - async: 后台 Worker 调用
        """
        if self._text_loading:
            return

        try:
            plan = self._load_text_usecase.plan_load(source_key)
        except Exception as e:
            self._on_text_load_failed(
                f"加载文本失败：{GlobalExceptionHandler.handle(e)}"
            )
            return

        if plan.execution_mode == "sync":
            self._load_sync(source_key)
        else:
            self._load_async(source_key)

    def _load_sync(self, source_key: str) -> None:
        """同步执行文本加载。"""
        self._set_text_loading(True)
        try:
            result = self._load_text_usecase.load(source_key)
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

    def _load_async(self, source_key: str) -> None:
        """异步执行文本加载。"""
        self._set_text_loading(True)
        worker = TextLoadWorker(
            load_text_usecase=self._load_text_usecase,
            source_key=source_key,
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
        return self._runtime_config.get_text_source_options()

    def get_default_source_key(self) -> str:
        return self._runtime_config.default_text_source_key
