from typing import Protocol

from ..models.dto.trainer import TrainerCatalogItem, TrainerLexicon


class TrainerRepository(Protocol):
    """练单器词库仓储端口。"""

    def list_trainers(self) -> list[TrainerCatalogItem]: ...

    def load_lexicon(self, trainer_id: str, group_size: int) -> TrainerLexicon: ...

    def save_current_segment(self, trainer_id: str, segment_index: int) -> None: ...

    def load_current_segment(self, trainer_id: str) -> int | None: ...
