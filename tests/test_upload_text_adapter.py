"""UploadTextAdapter local persistence tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.backend.presentation.adapters.upload_text_adapter import UploadTextAdapter


def test_local_upload_writes_text_and_absolute_config_path(tmp_path: Path) -> None:
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"text_sources": {}}), encoding="utf-8")
    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        texts_dir=str(texts_dir),
        config_path=str(config_path),
    )

    adapter.upload("标题", "正文", "custom", to_local=True, to_cloud=False)

    text_path = texts_dir / "custom_标题.txt"
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert text_path.read_text(encoding="utf-8") == "正文"
    assert config_data["text_sources"]["custom"]["local_path"] == str(text_path)


def test_local_upload_sanitizes_source_key_before_building_filename(
    tmp_path: Path,
) -> None:
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"text_sources": {}}), encoding="utf-8")
    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        texts_dir=str(texts_dir),
        config_path=str(config_path),
    )
    results = []
    adapter.uploadFinished.connect(
        lambda success, message, text_id: results.append((success, message, text_id))
    )

    adapter.upload("标题", "正文", "../evil\\nested/source", True, False)

    written_files = list(texts_dir.rglob("*.txt"))
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    text_source = next(iter(config_data["text_sources"].values()))
    assert results[-1][0] is True
    assert len(written_files) == 1
    assert written_files[0].resolve().is_relative_to(texts_dir.resolve())
    assert written_files[0].read_text(encoding="utf-8") == "正文"
    assert ".." not in written_files[0].name
    assert "/" not in written_files[0].name
    assert "\\" not in written_files[0].name
    assert text_source["local_path"] == str(written_files[0])
