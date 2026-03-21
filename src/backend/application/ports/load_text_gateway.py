from typing import Protocol

from ...models.text_source import TextSource


class LoadTextGateway(Protocol):
    def get_source(self, source_key: str) -> TextSource | None: ...

    def fetch_from_network(
        self, url: str, fetcher_key: str | None = None
    ) -> str | None: ...

    def fetch_from_catalog(self, text_id: str) -> str | None: ...

    def fetch_from_clipboard(self) -> str: ...

    def fetch_from_local(self, path: str) -> str | None: ...
