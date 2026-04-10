from typing import Protocol

from ..models.dto.fetched_text import FetchedText
from ..models.dto.text_catalog_item import TextCatalogItem


class TextProvider(Protocol):
    def get_catalog(self) -> list[TextCatalogItem]: ...

    def fetch_text_by_key(self, source_key: str) -> FetchedText | None: ...
