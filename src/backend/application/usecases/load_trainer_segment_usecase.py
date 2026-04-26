from ...domain.services.trainer_service import TrainerService
from ...models.dto.trainer import TrainerSegment


class LoadTrainerSegmentUseCase:
    """练单器段落加载与导航用例。"""

    def __init__(self, service: TrainerService) -> None:
        self._service = service

    def load_segment(
        self,
        trainer_id: str,
        *,
        segment_index: int,
        group_size: int,
    ) -> TrainerSegment:
        return self._service.load_trainer(
            trainer_id,
            group_size=group_size,
            segment_index=segment_index,
        )

    def current_segment(self) -> TrainerSegment:
        return self._service.current_segment()

    def next_segment(self) -> TrainerSegment:
        return self._service.next_segment()

    def previous_segment(self) -> TrainerSegment:
        return self._service.previous_segment()

    def shuffle_current_group(self) -> TrainerSegment:
        return self._service.shuffle_current_group()
