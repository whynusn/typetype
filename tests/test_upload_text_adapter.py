"""UploadTextAdapter local persistence tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.backend.presentation.adapters.upload_text_adapter import UploadTextAdapter
from src.backend.config.runtime_config import RuntimeConfig


def _make_runtime_config(config_path: Path, **overrides) -> RuntimeConfig:
    """Create a RuntimeConfig backed by a temp config file for testing."""
    data = {"text_sources": {}, **overrides}
    config_path.write_text(json.dumps(data), encoding="utf-8")
    config = RuntimeConfig._from_dict(json.loads(config_path.read_text()))
    config._config_path = str(config_path)
    return config


def test_local_upload_writes_text_and_absolute_config_path(tmp_path: Path) -> None:
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config = _make_runtime_config(config_path)
    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        runtime_config=config,
        texts_dir=str(texts_dir),
    )

    adapter.upload("标题", "正文", "custom", to_local=True, to_cloud=False)

    text_path = texts_dir / "custom_标题.txt"
    assert text_path.read_text(encoding="utf-8") == "正文"
    assert config.get_text_source("custom_标题") is not None
    assert config.get_text_source("custom_标题").local_path == str(text_path)


def test_local_upload_sanitizes_source_key_before_building_filename(
    tmp_path: Path,
) -> None:
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config = _make_runtime_config(config_path)
    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        runtime_config=config,
        texts_dir=str(texts_dir),
    )
    results = []
    adapter.uploadFinished.connect(
        lambda success, message, text_id: results.append((success, message, text_id))
    )

    adapter.upload("标题", "正文", "../evil\\nested/source", True, False)

    written_files = list(texts_dir.rglob("*.txt"))
    assert results[-1][0] is True
    assert len(written_files) == 1
    assert written_files[0].resolve().is_relative_to(texts_dir.resolve())
    assert written_files[0].read_text(encoding="utf-8") == "正文"
    assert ".." not in written_files[0].name
    assert "/" not in written_files[0].name
    assert "\\" not in written_files[0].name
    entry = config.get_text_source("evil_nested_source_标题")
    assert entry is not None
    assert entry.local_path == str(written_files[0])


def test_upload_emits_config_updated_signal(tmp_path: Path):
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config = _make_runtime_config(config_path)
    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        runtime_config=config,
        texts_dir=str(texts_dir),
    )
    received = []
    adapter.configUpdated.connect(lambda: received.append(True))

    adapter.upload("T", "content", "custom", to_local=True, to_cloud=False)

    assert len(received) == 1


def test_upload_triggers_runtime_config_reload(tmp_path: Path):
    texts_dir = tmp_path / "texts"
    config_path = tmp_path / "config.json"
    config = _make_runtime_config(config_path, text_sources={"old": {"label": "Old"}})

    adapter = UploadTextAdapter(
        text_uploader=MagicMock(),
        runtime_config=config,
        texts_dir=str(texts_dir),
    )
    adapter.upload("New", "content", "custom", to_local=True, to_cloud=False)

    config.reload()
    assert "custom_New" in config.text_source_config.sources
    assert config.get_text_source("custom_New") is not None
    assert config.get_text_source("custom_New").label == "New"
