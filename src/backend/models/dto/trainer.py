from dataclasses import dataclass


@dataclass(frozen=True)
class TrainerCatalogItem:
    trainer_id: str
    title: str
    path: str
    entry_count: int
    modified_timestamp: float


@dataclass(frozen=True)
class TrainerLexicon:
    trainer_id: str
    title: str
    mode: str
    groups: tuple[tuple[str, ...], ...]
    group_size: int


@dataclass(frozen=True)
class TrainerSegment:
    trainer_id: str
    title: str
    content: str
    items: tuple[str, ...]
    index: int
    total: int
    mode: str
    group_size: int
