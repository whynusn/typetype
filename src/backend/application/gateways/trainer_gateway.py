from ...models.dto.trainer import TrainerCatalogItem, TrainerLexicon
from ...ports.trainer_repository import TrainerRepository


class TrainerGateway:
    """练单器应用层网关。"""

    def __init__(self, repository: TrainerRepository) -> None:
        self._repository = repository

    def list_trainers(self) -> list[TrainerCatalogItem]:
        return self._repository.list_trainers()

    def load_lexicon(self, trainer_id: str, group_size: int) -> TrainerLexicon:
        return self._repository.load_lexicon(trainer_id, group_size)

    def save_current_segment(self, trainer_id: str, segment_index: int) -> None:
        self._repository.save_current_segment(trainer_id, segment_index)

    def load_current_segment(self, trainer_id: str) -> int | None:
        return self._repository.load_current_segment(trainer_id)
