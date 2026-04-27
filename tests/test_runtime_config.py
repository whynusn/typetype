import os
import subprocess
import sys
import json
from pathlib import Path

from src.backend.models.dto.text_catalog_item import TextCatalogItem
from src.backend.config.runtime_config import RuntimeConfig


def test_runtime_config_from_dict_builds_sources_and_default_key():
    runtime_config = RuntimeConfig._from_dict(
        {
            "base_url": "https://example.com",
            "api_timeout": 12.5,
            "default_text_source_key": "remote",
            "text_sources": {
                "local": {
                    "label": "本地示例",
                    "local_path": "resources/texts/demo.txt",
                },
                "remote": {
                    "label": "远程示例",
                    "has_ranking": True,
                },
            },
        }
    )

    assert runtime_config.base_url == "https://example.com"
    assert runtime_config.api_timeout == 12.5
    assert runtime_config.default_text_source_key == "remote"

    local_source = runtime_config.get_text_source("local")
    assert local_source is not None
    assert local_source.label == "本地示例"
    assert local_source.local_path == "resources/texts/demo.txt"

    remote_source = runtime_config.get_text_source("remote")
    assert remote_source is not None
    assert remote_source.has_ranking is True


def test_runtime_config_source_options_include_catalog_items():
    runtime_config = RuntimeConfig._from_dict(
        {
            "default_text_source_key": "builtin_demo",
            "text_sources": {
                "builtin_demo": {
                    "label": "内置示例",
                    "local_path": "resources/texts/builtin_demo.txt",
                }
            },
        }
    )

    runtime_config.update_catalog(
        [
            TextCatalogItem(
                id=1,
                text_id="cloud_001",
                label="云端文章",
                description="每日推荐",
                has_ranking=False,
            )
        ]
    )

    assert runtime_config.get_text_source_options() == [
        {"key": "builtin_demo", "label": "内置示例"},
        {"key": "cloud_001", "label": "云端文章"},
    ]


def test_backend_config_modules_import_with_src_only_pythonpath(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend.config.runtime_config import RuntimeConfig; "
                "from backend.config.text_source_config import TextSourceEntry; "
                "from backend.models.dto.text_catalog_item import TextCatalogItem"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(repo_root / "src"),
            "HOME": str(isolated_home),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_update_base_url_persists_to_user_config(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    bundled_example = tmp_path / "bundle" / "config.example.json"
    bundled_example.parent.mkdir(parents=True)
    bundled_example.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    runtime_config = RuntimeConfig.load_from_file(str(bundled_example))

    runtime_config.update_base_url("http://new")

    assert user_config.exists()
    assert (
        json.loads(user_config.read_text(encoding="utf-8"))["base_url"] == "http://new"
    )
    assert (
        json.loads(bundled_example.read_text(encoding="utf-8"))["base_url"]
        == "http://old"
    )


def test_runtime_config_loads_default_wenlai_config_when_missing():
    config = RuntimeConfig._from_dict({})

    assert config.wenlai.base_url == "https://qingfawen.fcxxz.com"
    assert config.wenlai.length == 0
    assert config.wenlai.difficulty_level == 0
    assert config.wenlai.category == ""
    assert config.wenlai.segment_mode == "manual"
    assert config.wenlai.strict_length is False


def test_runtime_config_loads_wenlai_config_from_dict():
    config = RuntimeConfig._from_dict(
        {
            "wenlai": {
                "base_url": "https://example.test/",
                "length": 300,
                "difficulty_level": 5,
                "category": "classic",
                "segment_mode": "auto",
                "strict_length": True,
                "username": "alice",
                "display_name": "Alice",
                "user_id": 12,
            }
        }
    )

    assert config.wenlai.base_url == "https://example.test"
    assert config.wenlai.length == 300
    assert config.wenlai.difficulty_level == 5
    assert config.wenlai.category == "classic"
    assert config.wenlai.segment_mode == "auto"
    assert config.wenlai.strict_length is True
    assert config.wenlai.username == "alice"
    assert config.wenlai.display_name == "Alice"
    assert config.wenlai.user_id == 12


def test_runtime_config_malformed_wenlai_numbers_default_to_zero():
    config = RuntimeConfig._from_dict(
        {
            "wenlai": {
                "length": "bad",
                "difficulty_level": "bad",
                "user_id": "bad",
            }
        }
    )

    assert config.wenlai.length == 0
    assert config.wenlai.difficulty_level == 0
    assert config.wenlai.user_id == 0


def test_runtime_config_malformed_wenlai_strings_default_safely():
    config = RuntimeConfig._from_dict(
        {
            "wenlai": {
                "base_url": 123,
                "category": ["bad"],
                "segment_mode": {"bad": True},
                "username": 456,
                "display_name": None,
            }
        }
    )

    assert config.wenlai.base_url == "https://qingfawen.fcxxz.com"
    assert config.wenlai.category == ""
    assert config.wenlai.segment_mode == "manual"
    assert config.wenlai.username == ""
    assert config.wenlai.display_name == ""


def test_update_wenlai_config_persists_to_user_config(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    bundled_example = tmp_path / "bundle" / "config.example.json"
    bundled_example.parent.mkdir(parents=True)
    bundled_example.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    runtime_config = RuntimeConfig.load_from_file(str(bundled_example))
    runtime_config.update_wenlai_config(
        base_url="https://wenlai.test/",
        length=250,
        difficulty_level=4,
        category="wangwen",
        segment_mode="auto",
        strict_length=True,
    )

    saved = json.loads(user_config.read_text(encoding="utf-8"))["wenlai"]
    assert saved["base_url"] == "https://wenlai.test"
    assert saved["length"] == 250
    assert saved["difficulty_level"] == 4
    assert saved["category"] == "wangwen"
    assert saved["segment_mode"] == "auto"
    assert saved["strict_length"] is True


def test_update_wenlai_config_allows_empty_length(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    bundled_example = tmp_path / "bundle" / "config.example.json"
    bundled_example.parent.mkdir(parents=True)
    bundled_example.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    runtime_config = RuntimeConfig.load_from_file(str(bundled_example))
    runtime_config.update_wenlai_config(length=0)

    saved = json.loads(user_config.read_text(encoding="utf-8"))["wenlai"]
    assert runtime_config.wenlai.length == 0
    assert saved["length"] == 0
