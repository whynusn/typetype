import os
import subprocess
import sys
import json
from pathlib import Path

from RinUI.core.config import AppUIConfigManager, DEFAULT_CONFIG

from src.backend.config.runtime_config import RuntimeConfig


def test_runtime_config_from_dict_builds_sources_and_default_key():
    from src.backend.config.text_source_config import TextSourceEntry

    runtime_config = RuntimeConfig._from_dict(
        {
            "default_text_source_key": "local",
            "text_sources": {
                "local": {
                    "label": "本地示例",
                    "local_path": "resources/texts/demo.txt",
                },
            },
        }
    )

    assert runtime_config.default_text_source_key == "local"

    local_source = runtime_config.get_text_source("local")
    assert local_source is not None
    assert local_source.label == "本地示例"
    assert local_source.local_path == "resources/texts/demo.txt"
    assert isinstance(local_source, TextSourceEntry)
    # v2：所有来源均为本地文件，isLocal 恒 True
    assert local_source.is_local is True


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
                "from backend.config.text_source_config import TextSourceEntry"
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


def test_load_migrates_v1_file_and_stamps_schema_version(monkeypatch, tmp_path: Path):
    """v1 配置文件（缺 schema_version）加载时迁移写回并 stamp v2。"""
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_dir",
        lambda: tmp_path,  # 隔离真实 font_config.json 副作用
    )
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "api_timeout": 30.0,
                "text_sources": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    RuntimeConfig.load_from_file(str(user_config))

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert "base_url" not in saved
    assert "api_timeout" not in saved
    assert "registry" not in saved
    # 迁移只清理 v1 字段并 stamp，不物化全部缺省段（缺省由 _from_dict 补全）
    assert "reader_font_path" not in saved.get("ui", {})


def test_load_v2_file_does_not_rewrite(monkeypatch, tmp_path: Path):
    """已是 schema_version=2 的文件直接加载，不跑迁移（幂等）。"""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    v2 = RuntimeConfig()._to_dict()
    v2["custom_unknown"] = "keep-me"
    user_config.write_text(json.dumps(v2), encoding="utf-8")
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    mtime_before = user_config.stat().st_mtime_ns
    RuntimeConfig.load_from_file(str(user_config))
    mtime_after = user_config.stat().st_mtime_ns

    assert mtime_before == mtime_after, "v2 文件加载不应写回"
    assert (
        json.loads(user_config.read_text(encoding="utf-8"))["custom_unknown"]
        == "keep-me"
    )


def test_migrate_legacy_v1_full_sample(monkeypatch, tmp_path: Path):
    """v1 → v2 迁移全样例：server 字段删除、ott 收纳、text_sources 收敛、
    font_config.json 折叠、example.org 清理、stamp v2，且幂等。"""
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_dir",
        lambda: tmp_path,
    )
    (tmp_path / "font_config.json").write_text(
        json.dumps({"reader_font_path": "/fonts/old.ttf"}), encoding="utf-8"
    )

    raw = {
        "base_url": "https://server.example.com",
        "api_timeout": 20.0,
        "registry": {
            "primary_url": "https://cdn.example.com/old",
            "mirror_url": "",
            "cache_ttl_seconds": 7200,
            "max_content_bytes": 2048,
            "scripts_enabled": False,
        },
        "text_sources": {
            "local1": {
                "label": "本地一",
                "local_path": "/data/one.txt",
                "has_ranking": True,
            },
            "local2": {
                "label": "本地二",
                "loader": "local_file",
                "leaderboard_mode": "none",
                "local_path": "/data/two.txt",
            },
            "remote1": {
                "label": "远程",
                "loader": "remote_api",
                "source_type": "network",
            },
            "reg1": {"label": "注册表", "source_type": "registry"},
        },
        "source_repos": [
            {"url": "https://example.org/ott-repo.json", "enabled": True},
            {"url": "https://real.example.com/repo.json", "enabled": True},
        ],
        "ui": {"theme": {"current_theme": "Light"}},
        "wenlai": {"base_url": "https://wenlai.test"},
    }

    migrated = RuntimeConfig._migrate_legacy_v1(raw)

    assert migrated["schema_version"] == 2
    assert "base_url" not in migrated
    assert "api_timeout" not in migrated
    assert "registry" not in migrated
    assert migrated["ott"] == {
        "cache_ttl_seconds": 7200,
        "max_content_bytes": 2048,
        "scripts_enabled": False,
    }
    assert migrated["text_sources"] == {
        "local1": {"label": "本地一", "local_path": "/data/one.txt"},
        "local2": {"label": "本地二", "local_path": "/data/two.txt"},
    }
    assert "remote1" not in migrated["text_sources"]
    assert "reg1" not in migrated["text_sources"]
    assert [r["url"] for r in migrated["source_repos"]] == [
        "https://real.example.com/repo.json"
    ]
    # font_config.json 折叠
    assert migrated["ui"]["reader_font_path"] == "/fonts/old.ttf"
    assert migrated["ui"]["theme"]["current_theme"] == "Light"
    assert migrated["wenlai"]["base_url"] == "https://wenlai.test"
    # 幂等：对迁移结果再跑一次结果不变
    assert RuntimeConfig._migrate_legacy_v1(migrated) == migrated


def test_migrate_legacy_v1_does_not_override_existing_reader_font_path(
    monkeypatch, tmp_path: Path
):
    """ui.reader_font_path 已存在时不覆盖 font_config.json 的值。"""
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_dir",
        lambda: tmp_path,
    )
    (tmp_path / "font_config.json").write_text(
        json.dumps({"reader_font_path": "/fonts/old.ttf"}), encoding="utf-8"
    )

    migrated = RuntimeConfig._migrate_legacy_v1(
        {"ui": {"reader_font_path": "/fonts/new.ttf"}}
    )
    assert migrated["ui"]["reader_font_path"] == "/fonts/new.ttf"


def test_migrate_legacy_v1_font_config_missing_is_noop(monkeypatch, tmp_path: Path):
    """font_config.json 不存在时迁移不写 ui。"""
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_dir",
        lambda: tmp_path,
    )
    migrated = RuntimeConfig._migrate_legacy_v1(
        {"ui": {"theme": {"current_theme": "Dark"}}}
    )
    assert "reader_font_path" not in migrated["ui"]
    assert migrated["ui"]["theme"]["current_theme"] == "Dark"


def test_migration_from_old_registry_primary_url(tmp_path):
    """旧 registry.primary_url 在 v1→v2 迁移中被删除，不生成订阅（ADR-013 决策 5）。"""
    cfg = {
        "registry": {
            "primary_url": "https://cdn.example.com/old",
            "mirror_url": "",
            "cache_ttl_seconds": 7200,
            "max_content_bytes": 1048576,
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    # primary_url 不迁移为订阅；ott 收纳 cache_ttl_seconds
    assert not any(
        r.url == "https://cdn.example.com/old" for r in config.source_repos.repos
    )
    assert config.ott.cache_ttl_seconds == 7200
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert "registry" not in saved


def test_no_migration_overwrites_existing_source_repos(tmp_path):
    """已存在 source_repos（非 example.org）时迁移保留订阅。"""
    cfg = {
        "registry": {"primary_url": "https://cdn.example.com/old"},
        "source_repos": [{"url": "https://x.org/repo.json", "enabled": False}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].url == "https://x.org/repo.json"
    assert config.source_repos.repos[0].enabled is False


def test_ott_section_parsing():
    config = RuntimeConfig._from_dict(
        {"ott": {"cache_ttl_seconds": "7200", "max_content_bytes": 2048}}
    )
    assert config.ott.cache_ttl_seconds == 7200
    assert config.ott.max_content_bytes == 2048
    # 非法值回退默认
    config2 = RuntimeConfig._from_dict(
        {"ott": {"cache_ttl_seconds": "bad", "max_content_bytes": -1}}
    )
    assert config2.ott.cache_ttl_seconds == 3600
    assert config2.ott.max_content_bytes == 1_048_576
    # 缺省段回退默认
    config3 = RuntimeConfig._from_dict({})
    assert config3.ott.cache_ttl_seconds == 3600
    assert config3.ott.max_content_bytes == 1_048_576


def test_update_section_parsing():
    config = RuntimeConfig._from_dict(
        {
            "update": {
                "enabled": False,
                "auto_check": False,
                "check_interval_hours": 12,
                "channel": "beta",
                "mirrors": ["https://ghproxy.example/", ""],
            }
        }
    )
    assert config.update.enabled is False
    assert config.update.auto_check is False
    assert config.update.check_interval_hours == 12
    assert config.update.channel == "beta"
    assert config.update.mirrors == ["https://ghproxy.example/"]

    # 缺省段回退默认
    config2 = RuntimeConfig._from_dict({})
    assert config2.update.enabled is True
    assert config2.update.auto_check is True
    assert config2.update.check_interval_hours == 24
    assert config2.update.channel == "stable"
    assert config2.update.mirrors == []


def test_schema_version_to_dict_roundtrip():
    config = RuntimeConfig()
    assert config._to_dict()["schema_version"] == 2
    reloaded = RuntimeConfig._from_dict(config._to_dict())
    assert reloaded._to_dict()["schema_version"] == 2
    assert reloaded.ott.cache_ttl_seconds == config.ott.cache_ttl_seconds
    assert reloaded.update.check_interval_hours == config.update.check_interval_hours


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
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    runtime_config = RuntimeConfig.load_from_file(str(user_config))
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


def test_save_to_file_persists_text_sources_and_default_key(
    monkeypatch, tmp_path: Path
):
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "default_text_source_key": "old_default",
                "text_sources": {"old_src": {"label": "Old"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    config = RuntimeConfig.load_from_file(str(user_config))
    config.text_source_config.default_key = "new_default"

    from src.backend.config.text_source_config import TextSourceEntry

    config.text_source_config.sources["new_src"] = TextSourceEntry(
        key="new_src",
        label="New",
        local_path="/new.txt",
    )

    config._save_to_file()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert saved["default_text_source_key"] == "new_default"
    assert "new_src" in saved["text_sources"]
    assert saved["text_sources"]["new_src"] == {
        "label": "New",
        "local_path": "/new.txt",
    }
    # v2 序列化不含 loader/leaderboard_mode
    assert "loader" not in saved["text_sources"]["new_src"]


def test_text_sources_v2_to_dict_round_trip():
    config = RuntimeConfig._from_dict(
        {
            "text_sources": {
                "local": {
                    "label": "本地",
                    "local_path": "/tmp/a.txt",
                },
            },
        }
    )
    rt = config._to_dict()
    assert rt["text_sources"]["local"] == {
        "label": "本地",
        "local_path": "/tmp/a.txt",
    }
    assert "loader" not in rt["text_sources"]["local"]
    config2 = RuntimeConfig._from_dict(rt)
    source = config2.get_text_source("local")
    assert source is not None
    assert source.label == "本地"
    assert source.local_path == "/tmp/a.txt"


def test_reload_reflects_file_changes(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    init = {
        "text_sources": {
            "a": {"label": "A", "local_path": "/a.txt"},
        },
    }
    user_config.write_text(json.dumps(init), encoding="utf-8")
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))

    updated = {
        "text_sources": {
            "a": {"label": "A", "local_path": "/a.txt"},
            "b": {"label": "B", "local_path": "/new.txt"},
        },
        "ott": {"cache_ttl_seconds": 1234},
    }
    user_config.write_text(json.dumps(updated), encoding="utf-8")

    config.reload()
    assert "b" in config.text_source_config.sources
    source = config.get_text_source("b")
    assert source is not None
    assert source.local_path == "/new.txt"
    assert config.ott.cache_ttl_seconds == 1234


def test_update_wenlai_config_allows_empty_length(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    runtime_config = RuntimeConfig.load_from_file(str(user_config))
    runtime_config.update_wenlai_config(length=0)

    saved = json.loads(user_config.read_text(encoding="utf-8"))["wenlai"]
    assert runtime_config.wenlai.length == 0
    assert saved["length"] == 0


def test_update_text_source_adds_entry(monkeypatch, tmp_path: Path):
    """update_text_source() creates a local entry in memory and persists to file."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    config = RuntimeConfig.load_from_file(str(user_config))
    config.update_text_source("my_text", "我的文本", "/tmp/my.txt")

    entry = config.get_text_source("my_text")
    assert entry is not None
    assert entry.label == "我的文本"
    assert entry.local_path == "/tmp/my.txt"
    assert config.default_text_source_key == "my_text"

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert "my_text" in saved["text_sources"]
    assert saved["text_sources"]["my_text"] == {
        "label": "我的文本",
        "local_path": "/tmp/my.txt",
    }


def test_update_text_source_reuses_existing_default_key(monkeypatch, tmp_path: Path):
    """If a default_key already exists, update_text_source leaves it unchanged."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "default_text_source_key": "existing_default",
                "text_sources": {"existing_default": {"label": "Existing"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    config = RuntimeConfig.load_from_file(str(user_config))
    config.update_text_source("new_text", "New", "/tmp/new.txt")
    assert config.default_text_source_key == "existing_default", (
        "existing default_key must be preserved"
    )


def test_ensure_user_config_exists_merges_missing_sections(monkeypatch, tmp_path: Path):
    """When user config lacks sections from _to_dict(), merge adds them."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    # Old-style v1 config: only base_url + text_sources, missing ott/update/ai/...
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    RuntimeConfig.ensure_user_config_exists()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert "base_url" not in saved
    assert "registry" not in saved
    assert saved["text_sources"] == {}
    assert "ott" in saved
    assert "update" in saved
    assert "ai" in saved
    assert "text_session" in saved
    assert "wenlai" in saved


def test_ensure_user_config_exists_preserves_existing_values(
    monkeypatch, tmp_path: Path
):
    """When config has all sections already, merge preserves values unchanged."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://custom",
                "text_sources": {},
                "ai": {"provider": "custom", "base_url": "http://ai.test"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    RuntimeConfig.ensure_user_config_exists()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert "base_url" not in saved
    assert saved["ai"]["provider"] == "custom"
    assert saved["ai"]["base_url"] == "http://ai.test"
    assert saved["schema_version"] == 2


def test_ensure_user_config_exists_no_write_when_complete(monkeypatch, tmp_path: Path):
    """When config already has all sections, ensure_user_config_exists doesn't write."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    full = RuntimeConfig()._to_dict()
    user_config.write_text(json.dumps(full), encoding="utf-8")
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    mtime_before = user_config.stat().st_mtime_ns
    RuntimeConfig.ensure_user_config_exists()
    mtime_after = user_config.stat().st_mtime_ns

    assert mtime_before == mtime_after, "file must not be rewritten when complete"


def test_save_to_file_persists_all_to_dict_keys(monkeypatch, tmp_path: Path):
    """Every section in _to_dict() must also be persisted by _save_to_file()."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    config = RuntimeConfig.load_from_file(str(user_config))
    config._save_to_file()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    expected = config._to_dict()
    for key in expected:
        assert key in saved, (
            f"{key!r} is in _to_dict() but missing from _save_to_file() output"
        )


def test_save_to_file_uses_loaded_config_path(monkeypatch, tmp_path: Path):
    """A config loaded from an explicit path must write back to that path."""
    explicit_config = tmp_path / "explicit" / "config.json"
    user_config = tmp_path / "user" / "config.json"
    explicit_config.parent.mkdir(parents=True)
    user_config.parent.mkdir(parents=True)
    explicit_config.write_text(
        json.dumps({"base_url": "http://explicit", "text_sources": {}}),
        encoding="utf-8",
    )
    user_config.write_text(
        json.dumps({"base_url": "http://user", "text_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    config = RuntimeConfig.load_from_file(str(explicit_config))
    config.add_blocked_content_hash("sha256:abc")

    assert json.loads(explicit_config.read_text(encoding="utf-8"))[
        "blocked_content_hashes"
    ] == ["sha256:abc"]
    assert json.loads(user_config.read_text(encoding="utf-8"))["base_url"] == (
        "http://user"
    )


def test_rinui_ui_save_does_not_roll_back_runtime_subscriptions(tmp_path: Path):
    """RinUI exit-time UI save must not overwrite source_repos saved after load."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "text_sources": {},
                "source_repos": [],
                "wenlai": {"base_url": "https://old.wenlai"},
                "ai": {"base_url": "https://old.ai", "model": "old-model"},
            }
        ),
        encoding="utf-8",
    )

    ui_config = AppUIConfigManager(user_config, DEFAULT_CONFIG)
    runtime_config = RuntimeConfig.load_from_file(str(user_config))
    runtime_config.update_registry_url(primary_url="http://127.0.0.1:18888")
    runtime_config.update_wenlai_config(base_url="https://new.wenlai")
    runtime_config.update_ai_config(base_url="https://new.ai", model="new-model")

    ui_config.config["theme"]["current_theme"] = "Dark"
    ui_config.save_config()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert [r["url"] for r in saved["source_repos"]] == ["http://127.0.0.1:18888"]
    assert saved["wenlai"]["base_url"] == "https://new.wenlai"
    assert saved["ai"]["base_url"] == "https://new.ai"
    assert saved["ai"]["model"] == "new-model"
    assert saved["ui"]["theme"]["current_theme"] == "Dark"


# ---------------------------------------------------------------------------
# OTT Repo 控制面：SourceReposConfig + v1→v2 迁移
# ---------------------------------------------------------------------------


def test_source_repos_default_empty():
    config = RuntimeConfig()
    assert config.source_repos.repos == []
    assert config.source_repos.enabled_repos == []


def test_blocked_content_hashes_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = RuntimeConfig.load_from_file(str(path))
    config.add_blocked_content_hash("sha256:abc")
    config.add_blocked_content_hash("sha256:abc")
    config2 = RuntimeConfig.load_from_file(str(path))
    assert config2.blocked_content_hashes == ["sha256:abc"]
    assert config2.remove_blocked_content_hash("sha256:abc") is True
    config3 = RuntimeConfig.load_from_file(str(path))
    assert config3.blocked_content_hashes == []


def test_source_repo_last_snapshot_hash_roundtrip(tmp_path):
    """TUF-lite 快照参照字段持久化（ADR-011 Phase 3.6）。"""
    path = tmp_path / "config.json"
    config = RuntimeConfig.load_from_file(str(path))
    config.add_source_repo("https://snap.org/r.json")
    config.update_source_repo_refresh(
        "https://snap.org/r.json", last_snapshot_hash="sha256:abc"
    )

    config2 = RuntimeConfig.load_from_file(str(path))
    repo2 = next(
        r for r in config2.source_repos.repos if r.url == "https://snap.org/r.json"
    )
    assert repo2.last_snapshot_hash == "sha256:abc"

    # 空字段不写入 JSON（保持既有序列化风格）
    path2 = tmp_path / "config2.json"
    config3 = RuntimeConfig.load_from_file(str(path2))
    config3.add_source_repo("https://other.org/r.json")
    saved2 = json.loads(path2.read_text(encoding="utf-8"))
    other = next(
        r for r in saved2["source_repos"] if r["url"] == "https://other.org/r.json"
    )
    assert "last_snapshot_hash" not in other


def test_add_source_repo_dedup_and_enable():
    config = RuntimeConfig()
    config.add_source_repo("https://example.org/ott-repo.json")
    config.add_source_repo("https://example.org/ott-repo.json")  # 重复
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].url == "https://example.org/ott-repo.json"
    # 禁用后再 add → 重新启用而非新增
    config.set_source_repo_enabled("https://example.org/ott-repo.json", False)
    assert config.source_repos.repos[0].enabled is False
    config.add_source_repo("https://example.org/ott-repo.json")
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is True


def test_remove_and_toggle_source_repo():
    config = RuntimeConfig()
    config.add_source_repo("https://a.org/r.json")
    config.add_source_repo("https://b.org/r.json")
    assert config.remove_source_repo("https://a.org/r.json") is True
    assert len(config.source_repos.repos) == 1
    assert config.remove_source_repo("https://not.exist") is False
    config.set_source_repo_enabled("https://b.org/r.json", False)
    assert config.source_repos.enabled_repos == []


def test_update_registry_url_syncs_source_repo_subscription(tmp_path):
    """设置 Registry URL 必须同步落 source_repos 订阅，重启后地址不丢失。"""
    cfg = {
        "schema_version": 2,
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="http://127.0.0.1:18888")

    assert [r.url for r in config.source_repos.repos] == ["http://127.0.0.1:18888"]
    # 重新加载模拟重启：订阅保留
    config2 = RuntimeConfig.load_from_file(str(path))
    assert [r.url for r in config2.source_repos.repos] == ["http://127.0.0.1:18888"]


def test_update_registry_url_clear_removes_subscription(tmp_path):
    """清空 Registry URL（设置页语义"留空则禁用"）必须移除对应订阅。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="")
    assert config.source_repos.repos == []


def test_update_registry_url_change_removes_old_subscription(tmp_path):
    """更换 Registry URL 必须移除旧 primary 对应订阅，避免僵尸订阅。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="https://b.org/repo.json")

    assert [r.url for r in config.source_repos.repos] == ["https://b.org/repo.json"]
    # 模拟重启：订阅仅剩新地址
    config2 = RuntimeConfig.load_from_file(str(path))
    assert [r.url for r in config2.source_repos.repos] == ["https://b.org/repo.json"]


def test_update_registry_url_mirror_only_keeps_subscriptions(tmp_path):
    """仅改镜像（mirror-only）不得触碰订阅：禁用不被复活、删除不被重建。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    config.set_source_repo_enabled("https://a.org/repo.json", False)

    config.update_registry_url(mirror_url="http://mirror.example.org/m.json")
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is False

    # 删除订阅后再改镜像 → 不重建
    config.remove_source_repo("https://a.org/repo.json")
    config.update_registry_url(mirror_url="http://mirror2.example.org/m.json")
    assert config.source_repos.repos == []


def test_update_registry_url_whitespace_primary_does_not_create_empty_sub(
    tmp_path,
):
    """纯空格 primary_url 不得写入空 url 订阅（直接 API 调用场景）。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="   ")
    assert config.source_repos.repos == []


def test_update_registry_url_same_primary_keep_disabled_subscription(tmp_path):
    """同值重应用（primary 非空且未变，如仅改镜像）不得复活禁用订阅。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    config.set_source_repo_enabled("https://a.org/repo.json", False)

    config.update_registry_url(primary_url="https://a.org/repo.json")
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is False


def test_update_registry_url_after_panel_add_clear_and_change(tmp_path):
    """面板添加订阅后清空/换地址仍能移除旧主订阅（reviewer R1 自达路径）。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    # 设 A → 清空 → 面板加 B
    config.update_registry_url(primary_url="https://a.org/repo.json")
    config.update_registry_url(primary_url="")
    assert config.source_repos.repos == []
    config.add_source_repo("https://b.org/repo.json")
    assert [r.url for r in config.source_repos.repos] == ["https://b.org/repo.json"]

    # 再清空 → 移除 B（它是当前显示的主地址）
    config.update_registry_url(primary_url="")
    assert config.source_repos.repos == []

    # 面板再加 B → 换地址 → 移除 B，只留新地址
    config.add_source_repo("https://b.org/repo.json")
    config.update_registry_url(primary_url="https://c.org/repo.json")
    assert [r.url for r in config.source_repos.repos] == ["https://c.org/repo.json"]


def test_load_does_not_auto_subscribe_when_empty(tmp_path):
    """0.A7：空订阅配置加载后不自动订阅任何远程源，订阅必须用户显式添加。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert config.source_repos.repos == []


def test_load_migrates_away_example_org_placeholder(tmp_path):
    """0.A7：v1→v2 迁移仅清理 example.org 占位订阅，不清用户真实订阅。"""
    cfg = {
        "source_repos": [
            {"url": "https://example.org/ott-repo.json", "enabled": True},
            {"url": "https://real.example.com/repo.json", "enabled": True},
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert [r.url for r in config.source_repos.repos] == [
        "https://real.example.com/repo.json"
    ]


def test_load_self_heals_v2_stamped_with_v1_residue(monkeypatch, tmp_path: Path):
    """v2 stamp 但残留 v1 特征键（base_url/registry）+ example.org 订阅 → 自愈迁移。

    根因（2026-08-13 实测复现）：_save_to_file 合并未知字段保留了 v1 键，
    旧版 load_from_file 只按 schema_version 判断 → 残留永存、默认源为
    example.org（404）。修复：_needs_v1_migration 检测 v1 特征键补跑迁移。
    """
    # 模拟用户真实配置：schema_version=2 + v2 段 + 残留 base_url/registry/example.org
    cfg = {
        "schema_version": 2,
        "typing_history_max_records": 2000,
        "blocked_content_hashes": [],
        "text_sources": {},
        "default_text_source_key": "",
        "ott": {
            "cache_ttl_seconds": 3600,
            "max_content_bytes": 1048576,
            "scripts_enabled": True,
        },
        "update": {
            "enabled": True,
            "auto_check": True,
            "check_interval_hours": 24,
            "channel": "stable",
            "mirrors": [],
        },
        "source_repos": [{"url": "https://example.org/ott-repo.json", "enabled": True}],
        "base_url": "http://127.0.0.1:8080",  # ← v1 残留
        "api_timeout": 20.0,  # ← v1 残留
        "registry": {  # ← v1 残留
            "primary_url": "",
            "mirror_url": "",
            "cache_ttl_seconds": 3600,
            "max_content_bytes": 1048576,
            "scripts_enabled": True,
        },
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    config = RuntimeConfig.load_from_file(str(path))

    # 内存态：v1 特征键已从 dataclass 移除（无 base_url/registry 属性）；
    # example.org 占位已清，随后自动补默认订阅（builtin file:// + hub）
    assert not hasattr(config, "base_url")
    assert not hasattr(config, "registry")
    urls = [r.url for r in config.source_repos.repos]
    assert all("example.org" not in u for u in urls)
    assert any(u.startswith("file://") for u in urls)  # 内置离线源
    assert any("ott-source-hub" in u for u in urls)  # hub 订阅

    # 磁盘态：迁移写回为干净 v2（无 v1 键、无 example.org）
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert "base_url" not in saved
    assert "api_timeout" not in saved
    assert "registry" not in saved
    assert all("example.org" not in r["url"] for r in saved.get("source_repos", []))

    # 幂等：再次加载不再触发迁移/写回（mtime 不变）
    mtime_before = path.stat().st_mtime_ns
    RuntimeConfig.load_from_file(str(path))
    assert path.stat().st_mtime_ns == mtime_before

    # 默认订阅已持久化到磁盘：builtin file:// + hub 都在，下次启动不丢失
    saved2 = json.loads(path.read_text(encoding="utf-8"))
    urls2 = [r["url"] for r in saved2.get("source_repos", [])]
    assert any(u.startswith("file://") for u in urls2)
    assert any("ott-source-hub" in u for u in urls2)


def test_needs_v1_migration_detects_legacy_keys():
    """_needs_v1_migration：干净 v2 False；缺版本/残留键/非 dict True。"""
    assert not RuntimeConfig._needs_v1_migration(
        {"schema_version": 2, "source_repos": []}
    )
    assert RuntimeConfig._needs_v1_migration({"source_repos": []})  # 缺版本
    assert RuntimeConfig._needs_v1_migration(
        {"schema_version": 2, "base_url": "http://x"}
    )  # 残留 base_url
    assert RuntimeConfig._needs_v1_migration(
        {"schema_version": 2, "registry": {}}
    )  # 残留 registry
    assert RuntimeConfig._needs_v1_migration(None)
    assert RuntimeConfig._needs_v1_migration([])


def test_clean_v2_with_example_org_cleaned_on_every_load(tmp_path):
    """干净 v2（无 v1 特征键）但残留 example.org 订阅 → 每次加载清理并补默认订阅。

    2026-08-13 实测复现：历史版本 _save_to_file 合并未知字段把 example.org
    订阅写入干净 v2 配置；仅按 schema_version 判断迁移无法自愈（无 v1 键）。
    修复：_cleanup_stale_subscriptions 每次加载执行。
    """
    cfg = {
        "schema_version": 2,
        "source_repos": [{"url": "https://example.org/ott-repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    config = RuntimeConfig.load_from_file(str(path))

    urls = [r.url for r in config.source_repos.repos]
    assert all("example.org" not in u for u in urls)
    assert any(u.startswith("file://") for u in urls)  # 内置离线源
    assert any("ott-source-hub" in u for u in urls)  # hub 订阅

    # 清理结果已持久化：下次启动不会再有 example.org
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert all("example.org" not in r["url"] for r in saved.get("source_repos", []))


def test_clean_v2_without_example_org_not_rewritten(tmp_path):
    """干净 v2 且无 example.org → 加载不写回（幂等）。"""
    cfg = {
        "schema_version": 2,
        "source_repos": [
            {
                "url": "https://cdn.jsdelivr.net/gh/whynusn/ott-source-hub@main/ott-repo.json"
            }
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    mtime_before = path.stat().st_mtime_ns
    RuntimeConfig.load_from_file(str(path))
    assert path.stat().st_mtime_ns == mtime_before


def test_source_repos_serialization_roundtrip(tmp_path):
    config = RuntimeConfig()
    config.add_source_repo("https://example.org/ott-repo.json")
    config.set_source_repo_trust(
        "https://example.org/ott-repo.json", "verified", "ed25519:abc"
    )
    data = config._to_dict()
    assert data["source_repos"][0]["url"] == "https://example.org/ott-repo.json"
    assert data["source_repos"][0]["trust_state"] == "verified"
    assert data["source_repos"][0]["pinned_pubkey"] == "ed25519:abc"
    # 反序列化
    config2 = RuntimeConfig._from_dict(data)
    assert config2.source_repos.repos[0].url == "https://example.org/ott-repo.json"
    assert config2.source_repos.repos[0].trust_state == "verified"


def test_parse_source_repos_ignores_invalid_entries():
    config = RuntimeConfig._from_dict(
        {
            "source_repos": [
                {"url": "https://valid.org/r.json"},
                {"url": ""},  # 无效：空 URL
                "not-a-dict",  # 无效：非 dict
                {"enabled": True},  # 无效：缺 url
            ]
        }
    )
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].url == "https://valid.org/r.json"


def test_source_repo_pending_trust_state_accepted(tmp_path):
    """pending 作为合法 trust_state 被解析，且保留固定公钥。"""
    config = RuntimeConfig._from_dict(
        {
            "source_repos": [
                {
                    "url": "https://repo.example.com/r.json",
                    "trust_state": "pending",
                    "pinned_pubkey": "ed25519:abc",
                },
            ]
        }
    )
    config._config_path = str(tmp_path / "config.json")
    repo = config.source_repos.repos[0]
    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == "ed25519:abc"
    # 序列化 round-trip 保持 pending
    config2 = RuntimeConfig._from_dict(config._to_dict())
    assert config2.source_repos.repos[0].trust_state == "pending"


def test_confirm_source_repo_trust_sets_verified_keeps_pin(tmp_path):
    config = RuntimeConfig._from_dict(
        {
            "source_repos": [
                {
                    "url": "https://repo.example.com/r.json",
                    "trust_state": "pending",
                    "pinned_pubkey": "ed25519:abc",
                },
            ]
        }
    )
    config._config_path = str(tmp_path / "config.json")
    config.confirm_source_repo_trust("https://repo.example.com/r.json")
    repo = config.source_repos.repos[0]
    assert repo.trust_state == "verified"
    assert repo.pinned_pubkey == "ed25519:abc"


def test_reject_source_repo_trust_sets_unverified_clears_pin(tmp_path):
    config = RuntimeConfig._from_dict(
        {
            "source_repos": [
                {
                    "url": "https://repo.example.com/r.json",
                    "trust_state": "pending",
                    "pinned_pubkey": "ed25519:abc",
                },
            ]
        }
    )
    config._config_path = str(tmp_path / "config.json")
    config.reject_source_repo_trust("https://repo.example.com/r.json")
    repo = config.source_repos.repos[0]
    assert repo.trust_state == "unverified"
    assert repo.pinned_pubkey == ""
    # 订阅本身不被删除，仅回退信任状态
    assert len(config.source_repos.repos) == 1
    assert repo.url == "https://repo.example.com/r.json"


def test_ott_scripts_enabled_default_follows_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    cfg = RuntimeConfig()
    assert cfg.ott.scripts_enabled is True


def test_ott_scripts_enabled_default_disabled_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    cfg = RuntimeConfig()
    assert cfg.ott.scripts_enabled is False


def test_ott_scripts_enabled_from_dict():
    cfg_false = RuntimeConfig._from_dict({"ott": {"scripts_enabled": False}})
    assert cfg_false.ott.scripts_enabled is False
    cfg_str = RuntimeConfig._from_dict({"ott": {"scripts_enabled": "false"}})
    assert cfg_str.ott.scripts_enabled is False
    cfg_default = RuntimeConfig._from_dict({})
    assert cfg_default.ott.scripts_enabled == (sys.platform != "win32")


def test_update_scripts_enabled_persists_to_ott(monkeypatch, tmp_path: Path):
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps({"schema_version": 2, "source_repos": []}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))
    config.update_scripts_enabled(False)
    assert config.ott.scripts_enabled is False
    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["ott"]["scripts_enabled"] is False


# ---------------------------------------------------------------------------
# 写入链路审计修复（原子写 / ui 合并 / _safe_bool / _safe_float）
# ---------------------------------------------------------------------------


def test_save_to_file_atomic_on_serialize_error_preserves_original(
    monkeypatch, tmp_path: Path
):
    """json.dump 中途抛异常 → 磁盘 config.json 内容保持完好，无残留 .tmp。"""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {"base_url": "http://old", "text_sources": {}, "custom_unknown": 1},
            indent=4,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))
    original = user_config.read_text(encoding="utf-8")  # 迁移写回后的磁盘内容

    def boom(*args, **kwargs):
        raise RuntimeError("serialize boom")

    monkeypatch.setattr("src.backend.config.runtime_config.json.dump", boom)
    config._save_to_file()

    assert user_config.read_text(encoding="utf-8") == original
    assert not user_config.with_name(user_config.name + ".tmp").exists()


def test_save_preserves_rinui_direct_ui_write(monkeypatch, tmp_path: Path):
    """AppUIConfigManager 直写磁盘的新 ui 主题，在 RuntimeConfig 保存时不被覆盖。"""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "ui": {"theme": {"current_theme": "Light"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))

    # 模拟 RinUI AppUIConfigManager 不经 RuntimeConfig 直写磁盘
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "ui": {"theme": {"current_theme": "Dark"}},
            }
        ),
        encoding="utf-8",
    )
    config.add_source_repo("https://repo.example.org/r.json")

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["ui"]["theme"]["current_theme"] == "Dark"
    assert any(
        r["url"] == "https://repo.example.org/r.json" for r in saved["source_repos"]
    )


def test_update_ui_config_overrides_disk_ui_on_save(monkeypatch, tmp_path: Path):
    """update_ui_config() 后保存 → 磁盘 ui 是 RuntimeConfig 写的值（含本实例快照）。"""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "ui": {"theme": {"current_theme": "Light"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))

    # 磁盘被外部（AppUIConfigManager）改成 Dark，但 RuntimeConfig 随后
    # update_ui_config → 以本实例值（Light 快照 + 新键）整体写出
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "ui": {"theme": {"current_theme": "Dark"}},
            }
        ),
        encoding="utf-8",
    )
    config.update_ui_config(reader_font_path="/new/font.ttf")

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["ui"]["reader_font_path"] == "/new/font.ttf"
    assert saved["ui"]["theme"]["current_theme"] == "Light"


def test_source_repo_enabled_string_false_is_not_truthy():
    """手写 \"enabled\": \"false\"（字符串）必须解析为 False，而非被 bool() 判为 True。"""
    config = RuntimeConfig._from_dict(
        {"source_repos": [{"url": "https://a.org/r.json", "enabled": "false"}]}
    )
    assert config.source_repos.repos[0].enabled is False
    assert config.source_repos.enabled_repos == []

    # _safe_bool 全语义
    assert RuntimeConfig._safe_bool("true", False) is True
    assert RuntimeConfig._safe_bool("TRUE", False) is True
    assert RuntimeConfig._safe_bool("1", False) is True
    assert RuntimeConfig._safe_bool("yes", False) is True
    assert RuntimeConfig._safe_bool("false", True) is False
    assert RuntimeConfig._safe_bool("0", True) is False
    assert RuntimeConfig._safe_bool("no", True) is False
    assert RuntimeConfig._safe_bool("", True) is False
    assert RuntimeConfig._safe_bool(0, True) is False
    assert RuntimeConfig._safe_bool(5, False) is True
    assert RuntimeConfig._safe_bool("garbage", True) is True
    assert RuntimeConfig._safe_bool(None, True) is True


def test_text_sources_null_loads_as_empty(tmp_path: Path):
    """text_sources 为 null / 列表时不崩，按空 sources 处理。"""
    config = RuntimeConfig._from_dict({"text_sources": None})
    assert config.text_source_config.sources == {}
    config2 = RuntimeConfig._from_dict({"text_sources": []})
    assert config2.text_source_config.sources == {}

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"text_sources": None}), encoding="utf-8")
    config3 = RuntimeConfig.load_from_file(str(cfg_path))
    assert config3.text_source_config.sources == {}


def test_ai_timeout_float_precision_roundtrip():
    """ai.timeout 浮点精度往返不丢（30.5 不被 int() 截断成 30.0）。"""
    config = RuntimeConfig._from_dict({"ai": {"timeout": 30.5}})
    assert config.ai.timeout == 30.5
    config2 = RuntimeConfig._from_dict(config._to_dict())
    assert config2.ai.timeout == 30.5

    # 数字字符串同样按 float 解析，不截断
    config3 = RuntimeConfig._from_dict({"ai": {"timeout": "12.75"}})
    assert config3.ai.timeout == 12.75

    # 非法值回退默认
    config4 = RuntimeConfig._from_dict({"ai": {"timeout": "abc"}})
    assert config4.ai.timeout == 30.0
    assert RuntimeConfig._safe_float("3.25", 1.0) == 3.25
    assert RuntimeConfig._safe_float(None, 1.0) == 1.0
    assert RuntimeConfig._safe_float("oops", 1.0) == 1.0


# ---------------------------------------------------------------------------
# 用户 per-source 刷新间隔覆盖（source_refresh_overrides）
# ---------------------------------------------------------------------------


class TestSourceRefreshOverrides:
    def test_default_empty(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        assert cfg.source_refresh_overrides == {}

    def test_set_and_get(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        assert cfg.get_source_refresh_override("auth:1") == {
            "mode": "interval",
            "interval_seconds": 3600,
        }

    def test_invalid_mode_ignored(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "bogus", 10)
        assert cfg.get_source_refresh_override("auth:1") is None

    def test_clear_removes(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 60)
        cfg.clear_source_refresh_override("auth:1")
        assert cfg.get_source_refresh_override("auth:1") is None

    def test_roundtrip_to_dict(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        d = cfg._to_dict()
        assert d["source_refresh_overrides"] == {
            "auth:1": {"mode": "interval", "interval_seconds": 3600}
        }

    def test_load_from_file_roundtrip(self, tmp_path):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg._to_dict()), encoding="utf-8")
        loaded = RuntimeConfig.load_from_file(str(p))
        assert loaded.get_source_refresh_override("auth:1") == {
            "mode": "interval",
            "interval_seconds": 3600,
        }

    def test_from_dict_tolerates_bad_values(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        d = cfg._to_dict()
        d["source_refresh_overrides"] = {
            "auth:1": {"mode": "interval", "interval_seconds": "not-a-number"},
            "auth:2": "garbage",
        }
        parsed = RuntimeConfig._from_dict(d)
        assert parsed.get_source_refresh_override("auth:1") is None
        assert parsed.get_source_refresh_override("auth:2") is None

    def test_static_override_roundtrips(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:s", "static", 0)
        d = cfg._to_dict()
        parsed = RuntimeConfig._from_dict(d)
        assert parsed.get_source_refresh_override("auth:s") == {"mode": "static"}

    def test_on_demand_override_roundtrips(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:o", "on_demand", 0)
        parsed = RuntimeConfig._from_dict(cfg._to_dict())
        assert parsed.get_source_refresh_override("auth:o") == {"mode": "on_demand"}

    def test_interval_override_roundtrips(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:i", "interval", 3600)
        parsed = RuntimeConfig._from_dict(cfg._to_dict())
        assert parsed.get_source_refresh_override("auth:i") == {
            "mode": "interval",
            "interval_seconds": 3600,
        }
