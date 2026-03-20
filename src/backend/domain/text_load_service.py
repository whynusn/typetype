from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ..application.usecases.text_usecase import TextUseCase
from ..config.runtime_config import RuntimeConfig
from ..workers.text_load_worker import TextLoadWorker


class TextLoadService(QObject):
    """文本加载领域服务。

    负责：
    - 按来源类型（network/local/clipboard）路由加载请求
    - 异步网络文本加载（Worker 线程）
    - 同步本地/剪贴板加载
    - 加载状态管理
    """

    # ==== 信号定义 ====
    textLoaded = Signal(str)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()

    def __init__(
        self,
        text_usecase: TextUseCase,
        runtime_config: RuntimeConfig,
    ):
        super().__init__()
        self._text_usecase = text_usecase
        self._runtime_config = runtime_config
        self._text_loading = False
        self._thread_pool = QThreadPool.globalInstance()

    # ==== 私有方法 ====

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def _request_load_text_from_network(self, source_key: str) -> None:
        if self._text_loading:
            return

        url = self._runtime_config.get_text_source_url(source_key)
        if not url:
            self.textLoadFailed.emit(f"加载文本失败：未知载文来源({source_key})")
            return

        self._set_text_loading(True)
        worker = TextLoadWorker(
            text_usecase=self._text_usecase,
            url=url,
        )
        worker.signals.succeeded.connect(self._on_text_loaded)
        worker.signals.failed.connect(self._on_text_load_failed)
        worker.signals.finished.connect(self._on_text_load_finished)
        self._thread_pool.start(worker)

    def _request_load_text_from_local(self, source_key: str) -> None:
        path = self._runtime_config.get_local_path(source_key)
        if not path:
            self._on_text_load_failed(f"加载文本失败：本地来源缺少路径({source_key})")
            return
        text = self._text_usecase.load_text_from_local(path)
        if text is None:
            self._on_text_load_failed(f"加载文本失败：无法读取本地文章({source_key})")
            return
        self._on_text_loaded(text)

    # ==== Slot 入口 ====

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        source_type = self._runtime_config.get_text_source_type(source_key)
        if source_type == "network":
            self._request_load_text_from_network(source_key)
            return

        if source_type == "local":
            self._request_load_text_from_local(source_key)
            return

        self.textLoadFailed.emit(f"加载文本失败：未知载文来源类型({source_key})")

    # ==== 回调处理 ====

    @Slot(object)
    def _on_text_loaded(self, text: object) -> None:
        if text is None:
            self.textLoadFailed.emit("加载文本失败：未获取到文本")
            return
        if not isinstance(text, str):
            self.textLoadFailed.emit("加载文本失败：返回数据格式错误")
            return
        self.textLoaded.emit(text)

    @Slot(str)
    def _on_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    @Slot()
    def _on_text_load_finished(self) -> None:
        self._set_text_loading(False)

    @Slot()
    def loadTextFromClipboard(self) -> None:
        if self._text_loading:
            return

        self._set_text_loading(True)
        try:
            text = self._text_usecase.load_text_from_clipboard()
            self.textLoaded.emit(text)
        except Exception as e:
            self.textLoadFailed.emit(f"加载文本失败：{str(e)}")
        finally:
            self._set_text_loading(False)

    # ==== 属性代理 ====

    @property
    def text_loading(self) -> bool:
        return self._text_loading
