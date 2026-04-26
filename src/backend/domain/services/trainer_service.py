from dataclasses import dataclass
from random import Random

from ...models.dto.trainer import TrainerLexicon, TrainerSegment
from ...ports.trainer_repository import TrainerRepository


@dataclass
class _TrainerSession:
    lexicon: TrainerLexicon
    groups: list[list[str]]
    index: int


class TrainerService:
    """练单器当前词库与段落状态。"""

    def __init__(
        self,
        repository: TrainerRepository,
        randomizer: Random | None = None,
    ) -> None:
        self._repository = repository
        self._randomizer = randomizer or Random()
        self._session: _TrainerSession | None = None

    def load_trainer(
        self,
        trainer_id: str,
        *,
        group_size: int,
        segment_index: int | None = None,
    ) -> TrainerSegment:
        if group_size <= 0:
            raise ValueError("group_size must be greater than 0")

        lexicon = self._repository.load_lexicon(trainer_id, group_size)
        groups = [list(group) for group in lexicon.groups]
        desired_index = segment_index
        if desired_index is None:
            desired_index = self._repository.load_current_segment(trainer_id)
        index = self._clamp_index(desired_index or 1, len(groups))
        self._session = _TrainerSession(
            lexicon=lexicon,
            groups=groups,
            index=index,
        )
        self._save_progress()
        return self.current_segment()

    def current_segment(self) -> TrainerSegment:
        session = self._require_session()
        group = session.groups[session.index - 1] if session.groups else []
        return TrainerSegment(
            trainer_id=session.lexicon.trainer_id,
            title=session.lexicon.title,
            content="".join(group),
            items=tuple(group),
            index=session.index,
            total=max(1, len(session.groups)),
            mode=session.lexicon.mode,
            group_size=session.lexicon.group_size,
        )

    def next_segment(self) -> TrainerSegment:
        session = self._require_session()
        session.index = self._clamp_index(session.index + 1, len(session.groups))
        self._save_progress()
        return self.current_segment()

    def previous_segment(self) -> TrainerSegment:
        session = self._require_session()
        session.index = self._clamp_index(session.index - 1, len(session.groups))
        self._save_progress()
        return self.current_segment()

    def shuffle_current_group(self) -> TrainerSegment:
        session = self._require_session()
        if session.groups:
            self._randomizer.shuffle(session.groups[session.index - 1])
        return self.current_segment()

    def _require_session(self) -> _TrainerSession:
        if self._session is None:
            raise RuntimeError("trainer not loaded")
        return self._session

    def _save_progress(self) -> None:
        session = self._require_session()
        try:
            self._repository.save_current_segment(
                session.lexicon.trainer_id,
                session.index,
            )
        except OSError:
            pass

    def _clamp_index(self, index: int, group_count: int) -> int:
        total = max(1, group_count)
        return min(max(index, 1), total)
