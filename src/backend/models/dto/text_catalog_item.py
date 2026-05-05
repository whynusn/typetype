from dataclasses import dataclass


@dataclass
class TextCatalogItem:
    id: int
    source_key: str
    label: str
    description: str = ""
    has_ranking: bool = False
