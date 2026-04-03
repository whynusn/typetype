from typing import Protocol

from config.text_source_config import TextCatalogItem


class TextProvider(Protocol):
    def get_catalog(self) -> list[TextCatalogItem]: ...

    def fetch_text_by_key(self, source_key: str) -> str | None: ...
