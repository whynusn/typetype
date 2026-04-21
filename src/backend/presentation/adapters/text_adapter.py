from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...application.usecases.load_text_usecase import (
    LoadTextResult,
    LoadTextUseCase,
    TextLoadPlan,
)
from ...config.runtime_config import RuntimeConfig
from ...workers.text_load_worker import TextLoadWorker

if TYPE_CHECKING:
    from ...ports.local_text_loader import LocalTextLoader


class TextAdapter(QObject):
    """文本加载 Qt 适配层。

    职责：
    - Qt 信号管理
    - 线程协调（所有加载均走后台 Worker，避免主线程阻塞）
    - 错误回传
    - UI 配置展示（来源选项、默认来源）

    不负责：
    - 业务路由决策（由 LoadTextUseCase + TextSourceGateway 负责）
    """

    # 信号定义
    textLoaded = Signal(str, int, str)  # (text_content, text_id, source_label)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()
    localTextIdResolved = Signal(int)  # 本地文本异步回查到的 text_id

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        load_text_usecase: LoadTextUseCase,
        local_text_loader: "LocalTextLoader",
    ):
        super().__init__()
        self._runtime_config = runtime_config
        self._load_text_usecase = load_text_usecase
        self._local_text_loader = local_text_loader
        self._text_loading = False
        self._thread_pool = QThreadPool.globalInstance()

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def _on_text_loaded(self, result: LoadTextResult) -> None:
        """处理文本加载成功。

        Args:
            result: LoadTextResult 对象
        """

        text = result.text if hasattr(result, "text") else str(result)
        text_id = result.text_id if hasattr(result, "text_id") else None
        source_label = result.source_label if hasattr(result, "source_label") else ""
        source_key = result.source_key if hasattr(result, "source_key") else ""
        if not isinstance(text, str):
            self.textLoadFailed.emit("加载文本失败：返回数据格式错误")
            return
        self.textLoaded.emit(text, text_id if text_id is not None else -1, source_label)

        # 本地文本 text_id=None 时，后台线程异步回查服务端 text_id
        if text_id is None and source_key:
            self._lookup_text_id_async(source_key, text)

    def _lookup_text_id_async(self, source_key: str, content: str) -> None:
        """后台线程异步回查服务端 text_id。"""
        import threading

        gateway = self._load_text_usecase._text_gateway

        def _do_lookup():
            try:
                resolved_id = gateway.lookup_text_id(source_key, content)
                if resolved_id is not None:
                    # 从 daemon thread 直接发射信号，Qt 自动走 QueuedConnection 到主线程的 slot
                    self.localTextIdResolved.emit(resolved_id)
            except Exception:
                pass

        threading.Thread(target=_do_lookup, daemon=True).start()

    def _on_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    def _on_text_load_finished(self) -> None:
        self._set_text_loading(False)

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        """请求加载文本。

        所有加载均走后台 Worker，包括本地文件加载。
        本地文件加载只读文件立即返回（text_id=None），服务端 text_id 通过
        后台线程异步回查，回查完成后自动 setTextId 使排行榜/成绩提交可用。
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

        self._load_async(plan)

    def _load_async(self, plan: TextLoadPlan) -> None:
        """异步执行文本加载（后台 Worker）。"""
        self._set_text_loading(True)
        worker = TextLoadWorker(
            load_text_usecase=self._load_text_usecase,
            plan=plan,
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
                self._on_text_loaded(result)
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
        """获取 UI 可选的来源列表（全部来源，用于载文下拉框）。"""
        return self._runtime_config.text_source_config.get_source_options()

    def get_ranking_source_options(self) -> list[dict[str, str]]:
        """获取有排行榜的来源列表（用于排行榜页面）。"""
        return [
            {"key": source.key, "label": source.label}
            for source in self._runtime_config.text_source_config.get_ranking_sources()
        ]

    def get_default_source_key(self) -> str:
        return self._runtime_config.text_source_config.default_key

    def get_default_source_label(self) -> str:
        """获取默认文本来源的 label。"""
        default_key = self._runtime_config.text_source_config.default_key
        source = self._runtime_config.text_source_config.get_source(default_key)
        if source:
            return source.label
        return ""

    def get_upload_source_options(self) -> list[dict[str, str]]:
        """获取可用于云端上传的来源列表（排除仅本地源）。"""
        return [
            {"key": source.key, "label": source.label}
            for source in self._runtime_config.text_source_config.sources.values()
            if not source.local_path  # 只保留没有 local_path 的服务端源
        ]

    def get_base_url(self) -> str:
        """获取当前 API 服务地址。"""
        return self._runtime_config.base_url
