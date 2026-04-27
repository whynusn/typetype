from dataclasses import dataclass


@dataclass(frozen=True)
class LocalArticleCatalogItem:
    article_id: str
    title: str
    path: str
    char_count: int
    modified_timestamp: float


@dataclass(frozen=True)
class LocalArticleSegment:
    article_id: str
    title: str
    content: str
    index: int
    total: int
