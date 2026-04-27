from random import Random

import pytest

from src.backend.domain.services.trainer_service import TrainerService
from src.backend.models.dto.trainer import TrainerLexicon


class FakeTrainerRepository:
    def __init__(self) -> None:
        self.lexicons = {
            "words": TrainerLexicon(
                trainer_id="words",
                title="词库",
                mode="fixed",
                groups=(("一", "二"), ("三", "四"), ("五",)),
                group_size=2,
            ),
            "variable": TrainerLexicon(
                trainer_id="variable",
                title="变长",
                mode="variable",
                groups=(("襄", "攘", "壤", "镶", "瓤"), ("罗", "萝", "箩", "锣", "椤")),
                group_size=2,
            ),
        }
        self.progress: dict[str, int] = {}
        self.saved: list[tuple[str, int]] = []

    def list_trainers(self):  # pragma: no cover - not used by service tests
        return []

    def load_lexicon(self, trainer_id: str, group_size: int) -> TrainerLexicon:
        lexicon = self.lexicons[trainer_id]
        return TrainerLexicon(
            trainer_id=lexicon.trainer_id,
            title=lexicon.title,
            mode=lexicon.mode,
            groups=lexicon.groups,
            group_size=group_size,
        )

    def save_current_segment(self, trainer_id: str, segment_index: int) -> None:
        self.progress[trainer_id] = segment_index
        self.saved.append((trainer_id, segment_index))

    def load_current_segment(self, trainer_id: str) -> int | None:
        return self.progress.get(trainer_id)


class ReversingRandom(Random):
    def shuffle(self, x):  # noqa: ANN001
        x.reverse()


def test_load_trainer_uses_saved_progress_and_returns_current_segment() -> None:
    repository = FakeTrainerRepository()
    repository.progress["words"] = 2
    service = TrainerService(repository=repository, randomizer=Random(0))

    segment = service.load_trainer("words", group_size=2)

    assert segment.trainer_id == "words"
    assert segment.title == "词库"
    assert segment.content == "三四"
    assert segment.items == ("三", "四")
    assert segment.index == 2
    assert segment.total == 3
    assert segment.mode == "fixed"
    assert repository.saved[-1] == ("words", 2)


def test_load_trainer_allows_explicit_segment_to_override_progress() -> None:
    repository = FakeTrainerRepository()
    repository.progress["words"] = 2
    service = TrainerService(repository=repository, randomizer=Random(0))

    segment = service.load_trainer("words", group_size=2, segment_index=99)

    assert segment.index == 3
    assert segment.content == "五"
    assert repository.saved[-1] == ("words", 3)


def test_next_and_previous_segment_clamp_to_available_range() -> None:
    repository = FakeTrainerRepository()
    service = TrainerService(repository=repository, randomizer=Random(0))
    service.load_trainer("words", group_size=2, segment_index=2)

    assert service.next_segment().index == 3
    assert service.next_segment().index == 3
    assert service.previous_segment().index == 2
    assert service.previous_segment().index == 1
    assert service.previous_segment().index == 1
    assert repository.saved[-1] == ("words", 1)


def test_shuffle_current_group_uses_injected_randomizer() -> None:
    repository = FakeTrainerRepository()
    service = TrainerService(repository=repository, randomizer=ReversingRandom())
    service.load_trainer("variable", group_size=2, segment_index=1)

    segment = service.shuffle_current_group()

    assert segment.items == ("瓤", "镶", "壤", "攘", "襄")
    assert segment.content == "瓤镶壤攘襄"


def test_current_segment_requires_loaded_trainer() -> None:
    service = TrainerService(repository=FakeTrainerRepository(), randomizer=Random(0))

    with pytest.raises(RuntimeError, match="trainer not loaded"):
        service.current_segment()


def test_load_trainer_rejects_invalid_group_size() -> None:
    service = TrainerService(repository=FakeTrainerRepository(), randomizer=Random(0))

    with pytest.raises(ValueError, match="group_size"):
        service.load_trainer("words", group_size=0)
