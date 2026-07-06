from dataclasses import dataclass


@dataclass
class TextCatalogItem:
    id: int
    source_key: str
    label: str
    description: str = ""
    charCount: int = 0
    has_ranking: bool = False
