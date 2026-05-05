from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from ...application.gateways.wenlai_gateway import WenlaiGateway
from ...application.usecases.load_wenlai_text_usecase import (
    LoadWenlaiTextUseCase,
    WenlaiLoadResult,
)
from ...models.dto.wenlai_dto import WenlaiText
from ...ports.wenlai_provider import WenlaiAuthRequiredError
from ...workers.base_worker import BaseWorker


class WenlaiAdapter(QObject):
    """晴发文 Qt 适配层。"""

    TEXT_REQUEST_TIMEOUT_MS = 30_000

    textLoaded = Signal(str, str)  # content, title
    loadFailed = Signal(str)
    loadingChanged = Signal()
    loginResult = Signal(bool, str)
    loginStateChanged = Signal()
    configChanged = Signal()
    difficultiesLoaded = Signal(list)
    categoriesLoaded = Signal(list)

    def __init__(
        self,
        gateway: WenlaiGateway,
        load_usecase: LoadWenlaiTextUseCase,
    ):
        super().__init__()
        self._gateway = gateway
        self._load_usecase = load_usecase
        self._thread_pool = QThreadPool.globalInstance()
        self._loading = False
        self._active_worker_count = 0
        self._active_workers: set[BaseWorker] = set()
        self._text_loading = False
        self._current_text: WenlaiText | None = None
        self._is_active = False
        self._text_request_generation = 0

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def text_loading(self) -> bool:
        return self._text_loading

    @property
    def logged_in(self) -> bool:
        return self._gateway.is_logged_in()

    @property
    def current_user(self) -> str:
        config = self._gateway.config
        return config.display_name or config.username

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def current_text(self) -> WenlaiText | None:
        return self._current_text

    def _next_text_request_generation(self) -> int:
        self._text_request_generation += 1
        return self._text_request_generation

    def _is_current_text_request(self, request_generation: int) -> bool:
        return request_generation == self._text_request_generation

    def clear_active(self) -> None:
        self._next_text_request_generation()
        self._set_text_loading(False)
        if self._current_text is None and not self._is_active:
            return
        self._current_text = None
        self._is_active = False
        self.configChanged.emit()

    @property
    def base_url(self) -> str:
        return self._gateway.config.base_url

    @property
    def length(self) -> int:
        return self._gateway.config.length

    @property
    def difficulty_level(self) -> int:
        return self._gateway.config.difficulty_level

    @property
    def category(self) -> str:
        return self._gateway.config.category

    @property
    def segment_mode(self) -> str:
        return self._gateway.config.segment_mode

    @property
    def strict_length(self) -> bool:
        return self._gateway.config.strict_length

    def _set_loading(self, loading: bool) -> None:
        if self._loading != loading:
            self._loading = loading
            self.loadingChanged.emit()

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.loadingChanged.emit()

    def _begin_worker(self) -> None:
        self._active_worker_count += 1
        self._set_loading(True)

    def _finish_worker(self) -> None:
        self._active_worker_count = max(0, self._active_worker_count - 1)
        self._set_loading(self._active_worker_count > 0)

    def _run_worker(
        self,
        task,
        error_prefix: str,
        *,
        connect_failed: bool = True,
    ) -> BaseWorker:
        self._begin_worker()
        worker = BaseWorker(task=task, error_prefix=error_prefix)
        self._track_worker(worker)
        if connect_failed:
            worker.signals.failed.connect(self._on_failed)
        worker.signals.finished.connect(self._finish_worker)
        self._thread_pool.start(worker)
        return worker

    def _track_worker(self, worker: BaseWorker) -> None:
        worker.setAutoDelete(False)
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda done=worker: self._release_worker(done))

    def _release_worker(self, worker: BaseWorker) -> None:
        self._active_workers.discard(worker)

    def _run_text_worker(self, task, error_prefix: str) -> BaseWorker | None:
        if self._text_loading:
            return None
        request_generation = self._next_text_request_generation()
        self._set_text_loading(True)
        QTimer.singleShot(
            self.TEXT_REQUEST_TIMEOUT_MS,
            lambda generation=request_generation: self._on_text_request_timeout(
                generation
            ),
        )
        worker = self._run_worker(task, error_prefix, connect_failed=False)
        worker.signals.succeeded.connect(
            lambda result, generation=request_generation: (
                self._on_text_loaded_for_request(generation, result)
            )
        )
        worker.signals.failed.connect(
            lambda message, generation=request_generation: (
                self._on_text_failed_for_request(generation, message)
            )
        )
        worker.signals.finished.connect(
            lambda generation=request_generation: self._finish_text_request(generation)
        )
        return worker

    def _finish_text_request(self, request_generation: int) -> None:
        if self._is_current_text_request(request_generation):
            self._set_text_loading(False)

    def _on_text_request_timeout(self, request_generation: int) -> None:
        if (
            not self._is_current_text_request(request_generation)
            or not self._text_loading
        ):
            return
        self._next_text_request_generation()
        self._set_text_loading(False)
        self.loadFailed.emit("晴发文请求超时，请稍后重试")

    def _on_failed(self, message: str) -> None:
        if self._is_auth_required_failure(message):
            self._handle_auth_required_failure()
        self.loadFailed.emit(message)

    def _is_auth_required_failure(self, message: str) -> bool:
        auth_markers = (
            "请先在设置页登录晴发文",
            "登录已过期",
            "认证失效",
            "未登录",
            "token",
            "401",
            WenlaiAuthRequiredError.__name__,
        )
        return any(marker in message for marker in auth_markers)

    def _handle_auth_required_failure(self) -> None:
        self._next_text_request_generation()
        self._set_text_loading(False)
        self._gateway.logout()
        self._current_text = None
        self._is_active = False
        self.loginStateChanged.emit()
        self.configChanged.emit()

    def _on_text_loaded(self, result: WenlaiLoadResult) -> None:
        self._current_text = result.text
        self._is_active = True
        self.configChanged.emit()
        self.textLoaded.emit(result.text.content, result.text.display_title)

    def _on_text_loaded_for_request(
        self,
        request_generation: int,
        result: WenlaiLoadResult,
    ) -> None:
        if not self._is_current_text_request(request_generation):
            return
        self._set_text_loading(False)
        self._on_text_loaded(result)

    def _on_text_failed_for_request(
        self,
        request_generation: int,
        message: str,
    ) -> None:
        if not self._is_current_text_request(request_generation):
            if self._is_auth_required_failure(message):
                self._handle_auth_required_failure()
            return
        self._set_text_loading(False)
        self._on_failed(message)

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        worker = self._run_worker(
            lambda: self._gateway.login(username, password),
            "晴发文登录失败",
        )
        worker.signals.succeeded.connect(self._on_login_succeeded)
        worker.signals.failed.connect(
            lambda message: self.loginResult.emit(False, message)
        )

    def _on_login_succeeded(self, _result) -> None:
        self.loginStateChanged.emit()
        self.loginResult.emit(True, "晴发文登录成功")
        self.refreshDifficulties()
        self.refreshCategories()

    @Slot()
    def logout(self) -> None:
        self._next_text_request_generation()
        self._set_text_loading(False)
        self._gateway.logout()
        self._current_text = None
        self._is_active = False
        self.configChanged.emit()
        self.loginStateChanged.emit()

    @Slot()
    def loadRandomText(self) -> None:
        self._run_text_worker(
            self._load_usecase.load_random,
            "晴发文载文失败",
        )

    @Slot()
    def loadNextSegment(self) -> None:
        self._load_adjacent("next")

    @Slot()
    def loadPrevSegment(self) -> None:
        self._load_adjacent("prev")

    def _load_adjacent(self, direction: str) -> None:
        if self._text_loading:
            return
        if self._current_text is None:
            self.loadFailed.emit("请先加载晴发文文本")
            return
        current_text = self._current_text
        self._run_text_worker(
            lambda: self._load_usecase.load_adjacent(current_text, direction),
            "晴发文换段失败",
        )

    @Slot()
    def refreshDifficulties(self) -> None:
        worker = self._run_worker(self._gateway.get_difficulties, "晴发文难度加载失败")
        worker.signals.succeeded.connect(self._on_difficulties_loaded)

    def _on_difficulties_loaded(self, items) -> None:
        self.difficultiesLoaded.emit(
            [{"id": item.id, "name": item.name, "count": item.count} for item in items]
        )

    @Slot()
    def refreshCategories(self) -> None:
        worker = self._run_worker(self._gateway.get_categories, "晴发文分类加载失败")
        worker.signals.succeeded.connect(self._on_categories_loaded)

    def _on_categories_loaded(self, items) -> None:
        self.categoriesLoaded.emit(
            [{"code": item.code, "name": item.name} for item in items]
        )

    @Slot(str, int, int, str, str, bool)
    def updateConfig(
        self,
        base_url: str,
        length: int,
        difficulty_level: int,
        category: str,
        segment_mode: str,
        strict_length: bool,
    ) -> None:
        self._gateway.update_config(
            base_url=base_url,
            length=length,
            difficulty_level=difficulty_level,
            category=category,
            segment_mode=segment_mode,
            strict_length=strict_length,
        )
        self.configChanged.emit()
