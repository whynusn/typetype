import shutil
from pathlib import Path

from ..models.dto.font_entry import FontEntry
from ..ports.font_repository import FontRepository
from ..utils.logger import log_info


class FileFontRepository(FontRepository):
    """基于用户目录的字体资源仓储。

    字体文件统一存放在用户目录（含首次运行时种子复制的内置字体）。
    此仓储不调用 QFontDatabase（非线程安全），
    字体注册与 family name 解析由上层（Adapter）在主线程完成。
    """

    _FONT_EXTENSIONS = {".ttf", ".otf"}

    def __init__(
        self,
        user_dir: str | Path,
        bundled_dir: str | Path | None = None,
    ) -> None:
        self._user_dir = Path(user_dir).expanduser().resolve()
        self._bundled_names: set[str] = set()
        if bundled_dir:
            bd = Path(bundled_dir).expanduser().resolve()
            if bd.exists():
                self._bundled_names = {
                    p.name
                    for p in bd.iterdir()
                    if p.is_file() and p.suffix.lower() in self._FONT_EXTENSIONS
                }

    def list_fonts(self) -> list[FontEntry]:
        return self._scan_dir(self._user_dir)

    def get_font_path(self, name: str) -> str | None:
        for entry in self._scan_dir(self._user_dir):
            if entry.name == name:
                return entry.file_path
        return None

    def add_font(self, source_path: str) -> FontEntry:
        src = Path(source_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"字体文件不存在: {src}")
        if src.suffix.lower() not in self._FONT_EXTENSIONS:
            raise ValueError(f"不支持的字体格式: {src.suffix}")

        self._user_dir.mkdir(parents=True, exist_ok=True)
        dest = self._user_dir / src.name
        if dest.exists():
            raise FileExistsError(f"字体文件已存在: {dest.name}")

        shutil.copy2(src, dest)
        log_info(f"[FileFontRepository] 字体文件已复制: {dest.name}")
        return FontEntry(
            name=dest.stem,
            file_path=str(dest),
            file_name=dest.name,
            is_bundled=False,
        )

    def remove_font(self, name: str) -> bool:
        for entry in self._scan_dir(self._user_dir):
            if entry.name == name:
                path = Path(entry.file_path)
                if path.exists():
                    path.unlink()
                    log_info(f"[FileFontRepository] 字体已删除: {name}")
                    return True
        return False

    def _scan_dir(self, directory: Path) -> list[FontEntry]:
        if not directory.exists():
            return []
        entries: list[FontEntry] = []
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in self._FONT_EXTENSIONS:
                entries.append(
                    FontEntry(
                        name=path.stem,
                        file_path=str(path),
                        file_name=path.name,
                        is_bundled=path.name in self._bundled_names,
                    )
                )
        return entries
