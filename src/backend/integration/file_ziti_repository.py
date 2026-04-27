from pathlib import Path

from ..models.dto.ziti import ZitiScheme, ZitiSchemeData
from ..ports.ziti_repository import ZitiRepository


class FileZitiRepository(ZitiRepository):
    """基于目录内 txt 文件的字提示方案仓储。"""

    def __init__(self, scheme_dir: str | Path) -> None:
        self._scheme_dir = Path(scheme_dir).expanduser().resolve()

    def list_schemes(self) -> list[ZitiScheme]:
        schemes: list[ZitiScheme] = []
        for path in self._scheme_paths():
            hints = self._parse_hints(self._read_text(path))
            schemes.append(ZitiScheme(name=path.stem, entry_count=len(hints)))
        return schemes

    def load_scheme(self, name: str) -> ZitiSchemeData:
        path = self._path_for_scheme(name)
        if path is None:
            raise FileNotFoundError(f"unknown ziti scheme: {name}")
        hints = self._parse_hints(self._read_text(path))
        return ZitiSchemeData(
            scheme=ZitiScheme(name=path.stem, entry_count=len(hints)),
            hints=hints,
        )

    def _scheme_paths(self) -> list[Path]:
        if not self._scheme_dir.exists():
            return []
        return sorted(
            [
                path
                for path in self._scheme_dir.glob("*.txt")
                if path.is_file() and not path.is_symlink()
            ],
            key=lambda path: path.name,
        )

    def _path_for_scheme(self, name: str) -> Path | None:
        for path in self._scheme_paths():
            if path.stem == name:
                return path
        return None

    def _read_text(self, path: Path) -> str:
        content = path.read_bytes()
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content.decode("gb18030")

    def _parse_hints(self, text: str) -> dict[str, str]:
        hints: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "\t" not in line:
                continue
            char, hint = line.split("\t", 1)
            char = char.strip().lstrip("\ufeff")
            hint = hint.strip()
            if char and hint:
                hints[char] = hint
        return hints
