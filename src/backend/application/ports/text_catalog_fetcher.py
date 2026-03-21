from typing import Protocol


class TextCatalogFetcher(Protocol):
    def fetch_text_by_id(self, text_id: str) -> str | None: ...
