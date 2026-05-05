from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.gateways.font_gateway import FontGateway
from ...models.dto.font_entry import FontEntry
from ...workers.base_worker import BaseWorker


class FontWorker(BaseWorker):
    """字体后台任务 Worker。"""

    pass


class FontAdapter(QObject):
    """字体资源 Qt 适配层。

    字体注册由 QML FontLoader 在 QML 层完成（线程安全），
    本类仅负责文件扫描、添加、删除，以及将文件信息传递给 QML。
    """

    fontsLoaded = Signal(list)
    fontsLoadFailed = Signal(str)
    fontAdded = Signal(bool, str)  # (success, message)
    fontRemoved = Signal(bool, str)  # (success, message)

    def __init__(self, gateway: FontGateway) -> None:
        super().__init__()
        self._gateway = gateway
        self._thread_pool = QThreadPool.globalInstance()

    def _list_fonts(self) -> list[FontEntry]:
        return self._gateway.list_fonts()

    def _on_fonts_scoped(self, entries: list[FontEntry]) -> None:
        """在主线程：将文件条目直接传递给 QML，不调用 QFontDatabase。"""
        result = [
            {
                "name": e.file_name,
                "filePath": e.file_path,
                "fileName": e.file_name,
                "isBundled": e.is_bundled,
            }
            for e in entries
        ]
        self.fontsLoaded.emit(result)

    @Slot()
    def loadFonts(self) -> None:
        worker = FontWorker(task=self._list_fonts, error_prefix="加载字体列表失败")
        worker.signals.succeeded.connect(self._on_fonts_scoped)
        worker.signals.failed.connect(self.fontsLoadFailed.emit)
        self._thread_pool.start(worker)

    @Slot(str)
    def addFont(self, file_path: str) -> None:
        def _do_add() -> FontEntry:
            return self._gateway.add_font(file_path)

        worker = FontWorker(task=_do_add, error_prefix="添加字体失败")

        def _on_added(entry: FontEntry) -> None:
            self.fontAdded.emit(True, f"字体添加成功: {entry.file_name}")

        worker.signals.succeeded.connect(_on_added)
        worker.signals.failed.connect(lambda msg: self.fontAdded.emit(False, msg))
        self._thread_pool.start(worker)

    @Slot(str)
    def removeFont(self, name: str) -> None:
        def _do_remove() -> bool:
            return self._gateway.remove_font(name)

        worker = FontWorker(task=_do_remove, error_prefix="删除字体失败")
        worker.signals.succeeded.connect(
            lambda _: self.fontRemoved.emit(True, f"已删除字体: {name}")
        )
        worker.signals.failed.connect(lambda msg: self.fontRemoved.emit(False, msg))
        self._thread_pool.start(worker)
