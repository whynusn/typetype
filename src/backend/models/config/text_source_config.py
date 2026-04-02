from dataclasses import dataclass, field


@dataclass
class TextSourceEntry:
    key: str
    label: str
    has_ranking: bool = False
    local_path: str | None = None
    text_id: str = ""


@dataclass
class TextCatalogItem:
    text_id: str
    label: str
    description: str = ""
    has_ranking: bool = False


@dataclass
class TextSourceConfig:
    sources: dict[str, TextSourceEntry] = field(default_factory=dict)
    default_key: str = ""
    catalog_items: list[TextCatalogItem] = field(default_factory=list)

    def get_source(self, key: str) -> TextSourceEntry | None:
        return self.sources.get(key)

    def get_default_source(self) -> TextSourceEntry | None:
        if self.default_key:
            return self.sources.get(self.default_key)
        return None

    def get_source_options(self) -> list[dict[str, str]]:
        options = [{"key": s.key, "label": s.label} for s in self.sources.values()]
        for item in self.catalog_items:
            options.append({"key": item.text_id, "label": item.label})
        return options

    def get_ranking_sources(self) -> list[TextSourceEntry]:
        return [s for s in self.sources.values() if s.has_ranking]

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        self.catalog_items = items
