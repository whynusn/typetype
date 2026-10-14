from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.exception_handler import GlobalExceptionHandler
from ...application.usecases.load_text_usecase import (
    LoadTextResult,
    LoadTextUseCase,
    TextLoadPlan,
)
from ...application.usecases.text_session_usecase import TextSessionUseCase
from ...config.runtime_config import RuntimeConfig
from ...models.dto.text_session import SegmentResult, TextHandle, TextKind
from ...workers.base_worker import BaseWorker, WorkerReleaseProxy, retain_worker
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
    localTextContentsLoaded = Signal(list)  # [{sourceKey, content}]
    localTextContentsLoadFailed = Signal(str)

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        load_text_usecase: LoadTextUseCase,
        local_text_loader: "LocalTextLoader",
        file_segment_provider_cls: "type | None" = None,
        in_memory_provider_cls: "type | None" = None,
    ):
        super().__init__()
        self._runtime_config = runtime_config
        self._load_text_usecase = load_text_usecase
        self._local_text_loader = local_text_loader
        # 由 container.py 装配注入的实现类（TextSessionUseCase 依赖端口协议，
        # 具体 provider 经此注入；None 时懒加载默认实现兜底）
        self._file_segment_provider_cls = file_segment_provider_cls
        self._in_memory_provider_cls = in_memory_provider_cls
        self._text_loading = False
        self._thread_pool = QThreadPool.globalInstance()
        self._load_generation = 0
        self._preview_generation = 0
        self._active_workers: set[BaseWorker] = set()
        self._release_proxies: dict[int, WorkerReleaseProxy] = {}

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def clear_active(self) -> None:
        """失效当前普通载文和本地预览 worker。"""
        self._load_generation += 1
        self._preview_generation += 1
        self._set_text_loading(False)

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
        if not isinstance(text, str):
            self.textLoadFailed.emit("加载文本失败：返回数据格式错误")
            return
        self.textLoaded.emit(text, text_id if text_id is not None else -1, source_label)

    def _on_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    def _on_text_load_finished(self) -> None:
        self._set_text_loading(False)

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        """请求加载文本。

        所有加载均走后台 Worker，包括本地文件加载。
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
        self._start_worker(worker)

    def _start_worker(self, worker: BaseWorker) -> None:
        """持有 worker 到 finished，确保跨线程信号不会因 GC 丢失。"""
        worker.setAutoDelete(False)
        self._active_workers.add(worker)
        proxy = WorkerReleaseProxy(self, worker, self._release_worker)
        self._release_proxies[id(worker)] = proxy
        worker.signals.finished.connect(proxy.release)
        # Adapter 可能在 worker 完成前被页面销毁；全局 manager 保证
        # WorkerSignals 在 queued signal 交付前仍然有效。
        retain_worker(worker)
        self._thread_pool.start(worker)

    def _release_worker(self, worker: BaseWorker) -> None:
        self._active_workers.discard(worker)
        self._release_proxies.pop(id(worker), None)

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
            self.clear_active()

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
                "isLocal": source.is_local,
            }
            for source in self._runtime_config.text_source_config.sources.values()
        ]

    def get_default_source_key(self) -> str:
        return self._runtime_config.text_source_config.default_key

    def get_startup_source_key(self) -> str:
        """启动自动载文优先选本地来源，避免远程默认源不可用时开屏报错。"""
        config = self._runtime_config.text_source_config
        default_key = config.default_key
        default_source = config.get_source(default_key)
        if default_source and default_source.is_local:
            return default_key

        for source in config.sources.values():
            if source.is_local:
                return source.key
        return default_key

    def get_default_source_label(self) -> str:
        """获取默认文本来源的 label。"""
        default_key = self._runtime_config.text_source_config.default_key
        source = self._runtime_config.text_source_config.get_source(default_key)
        if source:
            return source.label
        return ""

    @Slot(list)
    def requestLocalTextContents(self, source_keys: list[str]) -> None:
        """在后台批量读取本地来源预览，避免 QML 调用同步文件 I/O。"""
        self._preview_generation += 1
        preview_generation = self._preview_generation
        keys = list(dict.fromkeys(key for key in source_keys if isinstance(key, str)))
        source_specs: list[tuple[str, str | None]] = []
        for key in keys:
            source = self._runtime_config.text_source_config.get_source(key)
            source_specs.append((key, source.local_path if source else None))

        def load_contents() -> list[dict[str, str]]:
            contents: list[dict[str, str]] = []
            for key, path in source_specs:
                if not path:
                    contents.append({"sourceKey": key, "content": ""})
                    continue
                content = self._local_text_loader.load_text(path)
                contents.append({"sourceKey": key, "content": content or ""})
            return contents

        worker = BaseWorker(task=load_contents, error_prefix="读取本地文本失败")
        worker.signals.succeeded.connect(
            lambda contents, gen=preview_generation: (
                self.localTextContentsLoaded.emit(contents)
                if gen == self._preview_generation
                else None
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=preview_generation: (
                self.localTextContentsLoadFailed.emit(message)
                if gen == self._preview_generation
                else None
            )
        )
        self._start_worker(worker)

    def refresh_runtime_config(self) -> None:
        self._runtime_config.reload()

    @property
    def runtime_config(self) -> RuntimeConfig:
        """公共只读访问器：Bridge 等外部层经此读取配置，禁止直接触碰私有字段。"""
        return self._runtime_config

    def startFileTextSession(
        self,
        file_path: str,
        kind: TextKind,
        identifier: str,
        title: str,
        version: str,
        slice_size: int,
        start_slice: int = 1,
    ) -> "SegmentResult | None":
        """同步启动文件会话，供非 UI 工作线程或兼容入口使用。"""
        built = self.buildFileTextSession(
            file_path=file_path,
            kind=kind,
            identifier=identifier,
            title=title,
            version=version,
            slice_size=slice_size,
            start_slice=start_slice,
        )
        if built is None:
            return None
        usecase, result = built
        self.attachTextSession(usecase, slice_size)
        return result

    def buildFileTextSession(
        self,
        file_path: str,
        kind: TextKind,
        identifier: str,
        title: str,
        version: str,
        slice_size: int,
        start_slice: int = 1,
    ) -> "tuple[TextSessionUseCase, SegmentResult] | None":
        """构建文件会话但不替换当前会话，供 Worker 使用。"""
        if not file_path or slice_size <= 0:
            return None

        small_threshold = self._runtime_config.text_session.small_file_threshold
        provider_cls = self._file_segment_provider_cls
        if provider_cls is None:
            # 兼容直接构造（测试/独立使用）：懒加载默认实现
            from ...integration.file_segment_provider import FileSegmentProvider

            provider_cls = FileSegmentProvider
        provider = provider_cls(file_path, small_file_threshold=small_threshold)
        provider.load_index_cache()
        total_chars = provider.get_total_chars()
        if provider._index and not provider._text:
            provider.save_index_cache()

        handle = TextHandle(
            kind=kind,
            identifier=identifier,
            title=title,
            char_count=total_chars,
            version=version,
        )
        usecase = TextSessionUseCase(
            provider,
            handle,
            full_shuffle_threshold=self._runtime_config.text_session.full_shuffle_threshold,
            in_memory_provider_cls=self._in_memory_provider_cls,
        )
        return usecase, usecase.get_segment(start_slice, slice_size)

    def startProviderTextSession(
        self,
        provider,
        kind: TextKind,
        identifier: str,
        title: str,
        version: str,
        slice_size: int,
        start_slice: int = 1,
        source_key: str = "",
    ) -> "SegmentResult | None":
        """启动统一载文会话（任意 TextSegmentProvider）。"""
        built = self.buildProviderTextSession(
            provider=provider,
            kind=kind,
            identifier=identifier,
            title=title,
            version=version,
            slice_size=slice_size,
            start_slice=start_slice,
            source_key=source_key,
        )
        if built is None:
            return None
        usecase, result = built
        self.attachTextSession(usecase, slice_size)
        return result

    def buildProviderTextSession(
        self,
        provider,
        kind: TextKind,
        identifier: str,
        title: str,
        version: str,
        slice_size: int,
        start_slice: int = 1,
        source_key: str = "",
    ) -> "tuple[TextSessionUseCase, SegmentResult] | None":
        """构建任意 TextSegmentProvider 会话，不修改当前活动会话。"""
        if provider is None or slice_size <= 0:
            return None
        total_chars = provider.get_total_chars()
        handle = TextHandle(
            kind=kind,
            identifier=identifier,
            title=title,
            char_count=total_chars,
            version=version,
            source_key=source_key,
        )
        usecase = TextSessionUseCase(
            provider,
            handle,
            full_shuffle_threshold=self._runtime_config.text_session.full_shuffle_threshold,
            in_memory_provider_cls=self._in_memory_provider_cls,
        )
        result = usecase.get_segment(start_slice, slice_size)
        return usecase, result

    def attachTextSession(self, usecase: TextSessionUseCase, slice_size: int) -> None:
        """把已构建的文本会话设为当前活动会话。"""
        self._text_session_usecase = usecase
        self._session_slice_size = slice_size

    @property
    def text_session_usecase(self) -> TextSessionUseCase | None:
        return getattr(self, "_text_session_usecase", None)

    def get_text_session_segment(self, index: int) -> "SegmentResult | None":
        """从当前 TextSessionUseCase 按 1-based 索引取段。"""
        usecase = self.text_session_usecase
        if usecase is None:
            return None
        return usecase.get_segment(index, self._session_slice_size)
