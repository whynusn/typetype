import json
from pathlib import Path

import pytest

from src.backend.integration.file_trainer_repository import FileTrainerRepository


def test_list_trainers_returns_txt_files_with_stripped_display_names(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "10.后500.txt").write_text("后\n来\n", encoding="utf-8")
    (trainer_dir / "2.中500.txt").write_text("中\n间\n", encoding="utf-8")
    (trainer_dir / "plain.txt").write_text("plain\n", encoding="utf-8")
    (trainer_dir / "ignored.md").write_text("ignored\n", encoding="utf-8")
    repository = FileTrainerRepository(trainer_dir)

    trainers = repository.list_trainers()

    assert [(item.trainer_id, item.title, item.entry_count) for item in trainers] == [
        ("2.中500", "中500", 2),
        ("10.后500", "后500", 2),
        ("plain", "plain", 1),
    ]
    assert all(Path(item.path).is_absolute() for item in trainers)
    assert all(item.modified_timestamp > 0 for item in trainers)


def test_load_lexicon_decodes_utf8_and_groups_fixed_mode_by_lines(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "1.前500.txt").write_text("的\n一\n是\n了\n不\n", encoding="utf-8")
    repository = FileTrainerRepository(trainer_dir)

    lexicon = repository.load_lexicon("1.前500", group_size=2)

    assert lexicon.trainer_id == "1.前500"
    assert lexicon.title == "前500"
    assert lexicon.mode == "fixed"
    assert lexicon.groups == (("的", "一"), ("是", "了"), ("不",))


def test_load_lexicon_decodes_gb18030(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "gb.txt").write_bytes("中\n国\n".encode("gb18030"))
    repository = FileTrainerRepository(trainer_dir)

    lexicon = repository.load_lexicon("gb", group_size=10)

    assert lexicon.groups == (("中", "国"),)


def test_load_lexicon_uses_variable_mode_for_long_non_ascii_lines(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "16.要你命4000.txt").write_text(
        "襄攘壤镶瓤\n罗萝箩锣椤\n",
        encoding="utf-8",
    )
    repository = FileTrainerRepository(trainer_dir)

    lexicon = repository.load_lexicon("16.要你命4000", group_size=2)

    assert lexicon.mode == "variable"
    assert lexicon.groups == (
        ("襄", "攘", "壤", "镶", "瓤"),
        ("罗", "萝", "箩", "锣", "椤"),
    )


def test_ascii_first_line_stays_fixed_mode_even_when_long(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "18.english.txt").write_text(
        "alpha \nbeta \ngamma \n",
        encoding="utf-8",
    )
    repository = FileTrainerRepository(trainer_dir)

    lexicon = repository.load_lexicon("18.english", group_size=2)

    assert lexicon.mode == "fixed"
    assert lexicon.groups == (("alpha ", "beta "), ("gamma",))


def test_progress_is_persisted_under_trainer_directory(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    repository = FileTrainerRepository(trainer_dir)

    repository.save_current_segment("1.前500", 3)

    progress_file = trainer_dir / ".typetype_trainer_progress.json"
    assert progress_file.exists()
    assert json.loads(progress_file.read_text(encoding="utf-8")) == {
        "1.前500": {"current_segment": 3}
    }
    assert repository.load_current_segment("1.前500") == 3
    assert repository.load_current_segment("missing") is None


def test_corrupt_progress_file_is_ignored(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / ".typetype_trainer_progress.json").write_text(
        "{",
        encoding="utf-8",
    )
    repository = FileTrainerRepository(trainer_dir)

    assert repository.load_current_segment("1.前500") is None


def test_load_lexicon_rejects_unknown_trainer(tmp_path: Path) -> None:
    repository = FileTrainerRepository(tmp_path)

    with pytest.raises(FileNotFoundError, match="unknown trainer"):
        repository.load_lexicon("missing", group_size=10)


def test_load_lexicon_rejects_invalid_group_size(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "trainer"
    trainer_dir.mkdir()
    (trainer_dir / "words.txt").write_text("a\n", encoding="utf-8")
    repository = FileTrainerRepository(trainer_dir)

    with pytest.raises(ValueError, match="group_size"):
        repository.load_lexicon("words", group_size=0)
