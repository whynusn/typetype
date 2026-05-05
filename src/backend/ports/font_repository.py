from typing import Protocol

from ..models.dto.font_entry import FontEntry


class FontRepository(Protocol):
    """字体资源仓储端口。"""

    def list_fonts(self) -> list[FontEntry]: ...

    def get_font_path(self, name: str) -> str | None: ...

    def add_font(self, source_path: str) -> FontEntry: ...

    def remove_font(self, name: str) -> bool: ...
