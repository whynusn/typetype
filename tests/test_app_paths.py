"""Application path helpers tests."""

from pathlib import Path

from src.backend.config import app_paths


def test_macos_user_config_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.user_config_path()
        == tmp_path / "Library" / "Application Support" / "TypeType" / "config.json"
    )


def test_macos_char_stats_db_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.char_stats_db_path()
        == tmp_path / "Library" / "Application Support" / "TypeType" / "char_stats.db"
    )


def test_macos_typing_totals_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.typing_totals_path()
        == tmp_path
        / "Library"
        / "Application Support"
        / "TypeType"
        / "typing_totals.json"
    )


def test_macos_user_texts_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.user_texts_dir()
        == tmp_path / "Library" / "Application Support" / "TypeType" / "texts"
    )


def test_macos_user_trainer_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.user_trainer_dir()
        == tmp_path / "Library" / "Application Support" / "TypeType" / "trainer"
    )


def test_ensure_user_texts_seeded_copies_missing_txt_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)
    source_dir = tmp_path / "seed"
    source_dir.mkdir()
    (source_dir / "demo.txt").write_text("demo", encoding="utf-8")
    (source_dir / "ignored.md").write_text("ignored", encoding="utf-8")

    copied = app_paths.ensure_user_texts_seeded(source_dir)

    target_dir = app_paths.user_texts_dir()
    assert copied == 1
    assert (target_dir / "demo.txt").read_text(encoding="utf-8") == "demo"
    assert not (target_dir / "ignored.md").exists()


def test_ensure_user_texts_seeded_does_not_overwrite_existing_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)
    source_dir = tmp_path / "seed"
    source_dir.mkdir()
    (source_dir / "demo.txt").write_text("seed", encoding="utf-8")
    target_dir = app_paths.user_texts_dir()
    target_dir.mkdir(parents=True)
    (target_dir / "demo.txt").write_text("user", encoding="utf-8")

    copied = app_paths.ensure_user_texts_seeded(source_dir)

    assert copied == 0
    assert (target_dir / "demo.txt").read_text(encoding="utf-8") == "user"


def test_ensure_user_ziti_seeded_copies_missing_txt_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)
    source_dir = tmp_path / "ziti_seed"
    source_dir.mkdir()
    (source_dir / "小鹤.txt").write_text("一\tyi", encoding="utf-8")
    (source_dir / "ignored.md").write_text("ignored", encoding="utf-8")

    copied = app_paths.ensure_user_ziti_seeded(source_dir)

    target_dir = app_paths.user_ziti_dir()
    assert copied == 1
    assert (target_dir / "小鹤.txt").read_text(encoding="utf-8") == "一\tyi"
    assert not (target_dir / "ignored.md").exists()


def test_ensure_user_trainer_seeded_copies_missing_txt_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "src.backend.config.app_paths.platform.system", lambda: "Darwin"
    )
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)
    source_dir = tmp_path / "trainer_seed"
    source_dir.mkdir()
    (source_dir / "1.前500.txt").write_text("的\n一", encoding="utf-8")
    (source_dir / "ignored.md").write_text("ignored", encoding="utf-8")

    copied = app_paths.ensure_user_trainer_seeded(source_dir)

    target_dir = app_paths.user_trainer_dir()
    assert copied == 1
    assert (target_dir / "1.前500.txt").read_text(encoding="utf-8") == "的\n一"
    assert not (target_dir / "ignored.md").exists()


def test_linux_user_config_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.backend.config.app_paths.platform.system", lambda: "Linux")
    monkeypatch.setattr("src.backend.config.app_paths.Path.home", lambda: tmp_path)

    assert (
        app_paths.user_config_path()
        == tmp_path / ".config" / "typetype" / "config.json"
    )
