from typing import Protocol

from ...models.text_source import TextCatalogItem


class CatalogTextFetcher(Protocol):
    """文本目录协议，获取目录列表与按 ID 获取文本。"""

    def get_catalog(self) -> list[TextCatalogItem]: ...

    def fetch_text_by_id(self, text_id: str) -> str | None: ...
