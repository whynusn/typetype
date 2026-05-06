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

    删除策略：为避免 Qt FontLoader 仍 memory-map 字体文件时直接 unlink
    导致崩溃，删除操作仅将文件重命名为 ``.deleted`` 后缀；应用启动时
    调用 ``cleanup_deleted_fonts()`` 才真正清理物理文件。
    """

    _FONT_EXTENSIONS = {".ttf", ".otf"}
    _DELETED_SUFFIX = ".deleted"

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

        # 若此前同名字体被标记删除，先彻底清理残留，再复制新文件
        deleted = dest.with_suffix(dest.suffix + self._DELETED_SUFFIX)
        if deleted.exists():
            deleted.unlink()
            log_info(f"[FileFontRepository] 清理旧删除残留: {deleted.name}")

        shutil.copy2(src, dest)
        log_info(f"[FileFontRepository] 字体文件已复制: {dest.name}")
        return FontEntry(
            name=dest.stem,
            file_path=str(dest),
            file_name=dest.name,
            is_bundled=False,
        )

    def remove_font(self, name: str) -> bool:
        """将字体文件重命名为 ``.deleted`` 后缀（延迟删除），避免 Qt
        字体引擎仍在使用时直接 unlink 导致崩溃。"""
        for entry in self._scan_dir(self._user_dir):
            if entry.name == name:
                path = Path(entry.file_path)
                if path.exists():
                    deleted = path.with_suffix(path.suffix + self._DELETED_SUFFIX)
                    path.rename(deleted)
                    log_info(f"[FileFontRepository] 字体已标记删除: {name}")
                    return True
        return False

    def cleanup_deleted_fonts(self) -> None:
        """应用启动时调用：真正删除所有被标记为 ``.deleted`` 的字体文件。"""
        if not self._user_dir.exists():
            return
        for path in self._user_dir.iterdir():
            if path.is_file() and path.name.endswith(self._DELETED_SUFFIX):
                try:
                    path.unlink()
                    log_info(f"[FileFontRepository] 清理删除残留: {path.name}")
                except OSError:
                    pass

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
