from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.gateways.ziti_gateway import ZitiGateway
from ...models.dto.ziti import ZitiScheme, ZitiSchemeData
from ...workers.ziti_worker import ZitiWorker


class ZitiAdapter(QObject):
    """字提示 Qt 适配层。"""

    schemesLoaded = Signal(list)
    schemesLoadFailed = Signal(str)
    schemeLoaded = Signal(str, int)
    schemeLoadFailed = Signal(str)
    zitiStateChanged = Signal()

    def __init__(self, gateway: ZitiGateway) -> None:
        super().__init__()
        self._gateway = gateway
        self._thread_pool = QThreadPool.globalInstance()
        self._enabled = False
        self._current_scheme = ""
        self._hints: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def current_scheme(self) -> str:
        return self._current_scheme

    @property
    def loaded_count(self) -> int:
        return len(self._hints)

    def _scheme_to_dict(self, scheme: ZitiScheme) -> dict:
        return {"name": scheme.name, "entryCount": scheme.entry_count}

    def _list_schemes(self) -> list[dict]:
        return [self._scheme_to_dict(scheme) for scheme in self._gateway.list_schemes()]

    def _load_scheme(self, name: str) -> ZitiSchemeData:
        return self._gateway.load_scheme(name)

    def _on_schemes_loaded(self, schemes: list[dict]) -> None:
        self.schemesLoaded.emit(schemes)

    def _on_scheme_loaded(self, data: ZitiSchemeData) -> None:
        self._current_scheme = data.scheme.name
        self._hints = dict(data.hints)
        self.zitiStateChanged.emit()
        self.schemeLoaded.emit(data.scheme.name, len(self._hints))

    @Slot()
    def loadSchemes(self) -> None:
        worker = ZitiWorker(task=self._list_schemes, error_prefix="加载字提示方案失败")
        worker.signals.succeeded.connect(self._on_schemes_loaded)
        worker.signals.failed.connect(self.schemesLoadFailed.emit)
        self._thread_pool.start(worker)

    @Slot(str)
    def loadScheme(self, name: str) -> None:
        worker = ZitiWorker(
            task=lambda: self._load_scheme(name),
            error_prefix="加载字提示失败",
        )
        worker.signals.succeeded.connect(self._on_scheme_loaded)
        worker.signals.failed.connect(self.schemeLoadFailed.emit)
        self._thread_pool.start(worker)

    @Slot(bool)
    def setEnabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self.zitiStateChanged.emit()

    @Slot(str, result=str)
    def get_hint(self, char: str) -> str:
        if not char:
            return ""
        return self._hints.get(char[0], "")
