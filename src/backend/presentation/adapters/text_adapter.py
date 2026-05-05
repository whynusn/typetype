import threading
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
    localTextIdResolved = Signal(int, int)  # (text_id, lookup_generation)
    localTextIdLookupFailed = Signal()  # text_id 回查失败

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
        self._load_generation = 0
        self._lookup_generation = 0
        # text_id 回查调度：latest-only + single-flight
        self._lookup_lock = threading.Lock()
        self._lookup_inflight = False
        self._lookup_pending: tuple[str, str] | None = None
        self._lookup_latest_requested: tuple[str, str] | None = None

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def clear_active(self) -> None:
        """失效当前普通载文 worker 和 text_id 回查。"""
        self._load_generation += 1
        self.invalidate_pending_text_id_lookup()
        self._set_text_loading(False)

    def invalidate_pending_text_id_lookup(self) -> None:
        """失效仍在后台运行的 text_id 回查。"""
        self._lookup_generation += 1

    def _next_lookup_generation(self) -> int:
        self.invalidate_pending_text_id_lookup()
        return self._lookup_generation

    @property
    def current_lookup_generation(self) -> int:
        return self._lookup_generation

    def _next_load_generation(self) -> int:
        self._load_generation += 1
        return self._load_generation

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
        """后台线程异步回查服务端 text_id。

        调度策略：
        - latest-only：高频触发时只保留最新请求
        - single-flight：同一时刻仅 1 个回查线程在跑
        """
        lookup_generation = self._next_lookup_generation()
        request = (source_key, content, lookup_generation)
        should_start_worker = False
        with self._lookup_lock:
            self._lookup_latest_requested = request
            self._lookup_pending = request
            if not self._lookup_inflight:
                self._lookup_inflight = True
                should_start_worker = True

        if should_start_worker:
            threading.Thread(target=self._lookup_worker_loop, daemon=True).start()

    def _lookup_worker_loop(self) -> None:
        """串行消费 text_id 回查请求。"""
        usecase = self._load_text_usecase
        while True:
            with self._lookup_lock:
                request = self._lookup_pending
                self._lookup_pending = None

            if request is None:
                with self._lookup_lock:
                    self._lookup_inflight = False
                return

            source_key, content, lookup_generation = request
            try:
                if lookup_generation != self._lookup_generation:
                    continue
                resolved_id = usecase.lookup_text_id(source_key, content)
                should_emit = False
                with self._lookup_lock:
                    should_emit = request == self._lookup_latest_requested
                if (
                    resolved_id is not None
                    and lookup_generation == self._lookup_generation
                    and should_emit
                ):
                    # 从 daemon thread 直接发射信号，Qt 自动走 QueuedConnection 到主线程的 slot
                    self.localTextIdResolved.emit(resolved_id, lookup_generation)
            except Exception:
                # 回查失败不影响主流程（文本已显示），通知用户排行榜功能暂不可用
                if lookup_generation == self._lookup_generation:
                    self.localTextIdLookupFailed.emit()

    def lookup_text_id(self, source_key: str, content: str) -> None:
        """公开方法：后台异步回查服务端 text_id。

        用于 Bridge.loadFullText 等绕过 Worker 流程的直接载文路径，
        复用已有的 localTextIdResolved 信号链完成 text_id 回填。
        """
        self._lookup_text_id_async(source_key, content)

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
        self.invalidate_pending_text_id_lookup()

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
        load_generation = self._next_load_generation()
        worker = TextLoadWorker(
            load_text_usecase=self._load_text_usecase,
            plan=plan,
        )
        worker.signals.succeeded.connect(
            lambda result, gen=load_generation: self._on_text_loaded_for_request(
                gen, result
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=load_generation: self._on_text_load_failed_for_request(
                gen, message
            )
        )
        worker.signals.finished.connect(
            lambda gen=load_generation: self._on_text_load_finished_for_request(gen)
        )
        self._thread_pool.start(worker)

    def _on_text_loaded_for_request(
        self, load_generation: int, result: LoadTextResult
    ) -> None:
        if load_generation != self._load_generation:
            return
        self._on_text_loaded(result)

    def _on_text_load_failed_for_request(
        self, load_generation: int, message: str
    ) -> None:
        if load_generation != self._load_generation:
            return
        self._on_text_load_failed(message)

    def _on_text_load_finished_for_request(self, load_generation: int) -> None:
        if load_generation != self._load_generation:
            return
        self._on_text_load_finished()

    @Slot()
    def loadTextFromClipboard(self) -> None:
        """从剪贴板加载文本。"""
        if self._text_loading:
            return
        self.invalidate_pending_text_id_lookup()

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

    def get_source_options(self) -> list[dict[str, str | bool]]:
        """获取 UI 可选的来源列表（全部来源，用于载文下拉框）。"""
        return [
            {
                "key": source.key,
                "label": source.label,
                "isLocal": bool(source.local_path),
                "hasRanking": source.has_ranking,
            }
            for source in self._runtime_config.text_source_config.sources.values()
        ]

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

    def get_local_text_content(self, source_key: str) -> str:
        """读取指定本地来源的完整内容。"""
        source = self._runtime_config.text_source_config.get_source(source_key)
        if not source or not source.local_path:
            return ""

        try:
            return self._local_text_loader.load_text(source.local_path) or ""
        except Exception:
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
