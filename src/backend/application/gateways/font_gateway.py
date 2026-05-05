from ...models.dto.font_entry import FontEntry
from ...ports.font_repository import FontRepository


class FontGateway:
    """字体资源应用网关。"""

    def __init__(self, repository: FontRepository) -> None:
        self._repository = repository

    def list_fonts(self) -> list[FontEntry]:
        return self._repository.list_fonts()

    def get_font_path(self, name: str) -> str | None:
        return self._repository.get_font_path(name)

    def add_font(self, source_path: str) -> FontEntry:
        return self._repository.add_font(source_path)

    def remove_font(self, name: str) -> bool:
        return self._repository.remove_font(name)
