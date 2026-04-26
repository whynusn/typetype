from pathlib import Path

import pytest

from src.backend.integration.file_ziti_repository import FileZitiRepository


def test_list_schemes_returns_txt_files_with_entry_counts(tmp_path: Path) -> None:
    scheme_dir = tmp_path / "ziti"
    scheme_dir.mkdir()
    (scheme_dir / "小鹤.txt").write_text("一\tyi\n二\ter\n", encoding="utf-8")
    (scheme_dir / "ignore.md").write_text("x", encoding="utf-8")
    repository = FileZitiRepository(scheme_dir)

    schemes = repository.list_schemes()

    assert [(item.name, item.entry_count) for item in schemes] == [("小鹤", 2)]


def test_load_scheme_parses_tab_separated_hints_and_uses_last_duplicate(
    tmp_path: Path,
) -> None:
    scheme_dir = tmp_path / "ziti"
    scheme_dir.mkdir()
    (scheme_dir / "小鹤.txt").write_text(
        "\ufeff一\tyi\n# comment\n二\ter\n一\tyi2\nbad-line\n",
        encoding="utf-8",
    )
    repository = FileZitiRepository(scheme_dir)

    data = repository.load_scheme("小鹤")

    assert data.scheme.name == "小鹤"
    assert data.hints == {"一": "yi2", "二": "er"}


def test_load_scheme_decodes_gb18030(tmp_path: Path) -> None:
    scheme_dir = tmp_path / "ziti"
    scheme_dir.mkdir()
    (scheme_dir / "五笔.txt").write_bytes("中\tkhk\n".encode("gb18030"))
    repository = FileZitiRepository(scheme_dir)

    data = repository.load_scheme("五笔")

    assert data.hints == {"中": "khk"}


def test_load_scheme_rejects_unknown_scheme(tmp_path: Path) -> None:
    repository = FileZitiRepository(tmp_path)

    with pytest.raises(FileNotFoundError, match="unknown ziti scheme"):
        repository.load_scheme("missing")
