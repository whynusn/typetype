import sys
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice

from ..application.ports.local_text_loader import LocalTextLoader


class QtLocalTextLoader(LocalTextLoader):
    """基于 Qt QFile 的本地文本加载器，支持 qrc 与文件路径。"""

    def load_text(self, path: str) -> str | None:
        file_path = self._resolve_path(path)
        text_file = QFile(file_path)
        if not text_file.open(
            QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text
        ):
            return None

        try:
            data = bytes(text_file.readAll())
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("gb18030")
        except Exception:
            return None
        finally:
            text_file.close()

    def _resolve_path(self, path: str) -> str:
        if path.startswith("qrc:/"):
            return f":{path[4:]}"
        if Path(path).is_absolute():
            return path
        bundle_root = Path(sys.argv[0]).resolve().parent
        bundle_candidate = bundle_root / path
        if bundle_candidate.exists():
            return str(bundle_candidate)
        project_root = Path(__file__).resolve().parents[3]
        return str(project_root / path)
