from PySide6.QtCore import QObject, Signal, Slot

from ...application.gateways.font_gateway import FontGateway
from ...models.dto.font_entry import FontEntry


class FontAdapter(QObject):
    """字体资源 Qt 适配层。

    字体注册由 QML FontLoader 在 QML 层完成（线程安全），
    本类仅负责文件扫描、添加、删除，以及将文件信息传递给 QML。

    所有操作在主线程同步执行：字体文件操作（rename/copy/scan）
    均为本地微秒级 I/O，无需 worker 线程。worker 模式引入的
    QThreadPool + lambda 闭包生命周期问题曾导致 ``free(): invalid size``。
    """

    fontsLoaded = Signal(list)
    fontsLoadFailed = Signal(str)
    fontAdded = Signal(bool, str)  # (success, message)
    fontRemoved = Signal(bool, str)  # (success, message)

    def __init__(self, gateway: FontGateway) -> None:
        super().__init__()
        self._gateway = gateway

    def list_fonts(self) -> list[FontEntry]:
        return self._gateway.list_fonts()

    def _on_fonts_scoped(self, entries: list[FontEntry]) -> None:
        """将文件条目直接传递给 QML，不调用 QFontDatabase。"""
        result = [
            {
                # 必须与 FileFontRepository.remove_font 的匹配键一致：path.stem
                "name": e.name,
                "filePath": e.file_path,
                "fileName": e.file_name,
                "isBundled": e.is_bundled,
            }
            for e in entries
        ]
        self.fontsLoaded.emit(result)

    @Slot()
    def loadFonts(self) -> None:
        try:
            entries = self._gateway.list_fonts()
            self._on_fonts_scoped(entries)
        except Exception as e:
            self.fontsLoadFailed.emit(str(e))

    @Slot(str)
    def addFont(self, file_path: str) -> None:
        try:
            self._gateway.add_font(file_path)
            self.fontAdded.emit(True, "字体添加成功")
            self.loadFonts()
        except Exception as e:
            self.fontAdded.emit(False, str(e))

    @Slot(str)
    def removeFont(self, name: str) -> None:
        if not name:
            self.fontRemoved.emit(False, "字体名称不能为空")
            return
        try:
            ok = self._gateway.remove_font(name)
            if ok:
                self.fontRemoved.emit(True, f"已删除字体: {name}")
                self.loadFonts()
            else:
                self.fontRemoved.emit(False, f"字体不存在: {name}")
        except Exception as e:
            self.fontRemoved.emit(False, str(e))
