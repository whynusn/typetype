import os
import subprocess
import sys
import json
from pathlib import Path

from RinUI.core.config import AppUIConfigManager, DEFAULT_CONFIG

from src.backend.models.dto.text_catalog_item import TextCatalogItem
from src.backend.config.runtime_config import RuntimeConfig


def test_runtime_config_from_dict_builds_sources_and_default_key():
    from src.backend.config.text_source_config import (
        LeaderboardMode,
        Loader,
    )

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
    assert local_source.loader == Loader.LOCAL_FILE
    assert local_source.leaderboard_mode == LeaderboardMode.NONE

    remote_source = runtime_config.get_text_source("remote")
    assert remote_source is not None
    # 旧 has_ranking=True 对远程源映射为 SERVER_RESOLVED
    assert remote_source.loader == Loader.REMOTE_API
    assert remote_source.leaderboard_mode == LeaderboardMode.SERVER_RESOLVED


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
                source_key="cloud_001",
                label="云端文章",
                description="每日推荐",
                has_ranking=True,
            )
        ]
    )

    assert runtime_config.get_text_source_options() == [
        {"key": "builtin_demo", "label": "内置示例", "isLocal": True},
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

    runtime_config.update_base_url("http://new")

    assert user_config.exists()
    assert (
        json.loads(user_config.read_text(encoding="utf-8"))["base_url"] == "http://new"
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
                "api_timeout": 10.0,
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
    config.api_timeout = 99.0
    from src.backend.config.text_source_config import (
        LeaderboardMode,
        Loader,
        TextSourceEntry,
    )

    config.text_source_config.sources["new_src"] = TextSourceEntry(
        key="new_src",
        label="New",
        loader=Loader.LOCAL_FILE,
        leaderboard_mode=LeaderboardMode.NONE,
        local_path="/new.txt",
    )

    config._save_to_file()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["default_text_source_key"] == "new_default"
    assert saved["api_timeout"] == 99.0
    assert "new_src" in saved["text_sources"]
    assert saved["text_sources"]["new_src"]["label"] == "New"


def test_registry_source_type_survives_to_dict_round_trip():
    from src.backend.config.text_source_config import LeaderboardMode, Loader

    config = RuntimeConfig._from_dict(
        {
            "text_sources": {
                "registry_test": {
                    "label": "Registry",
                    "loader": "registry",
                    "leaderboard_mode": "server_resolved",
                },
            },
        }
    )
    rt = config._to_dict()
    assert rt["text_sources"]["registry_test"]["loader"] == "registry"
    config2 = RuntimeConfig._from_dict(rt)
    assert config2.get_text_source("registry_test") is not None
    assert config2.get_text_source("registry_test").loader == Loader.REGISTRY
    assert config2.get_text_source("registry_test").leaderboard_mode == (
        LeaderboardMode.SERVER_RESOLVED
    )


def test_reload_reflects_file_changes(monkeypatch, tmp_path: Path):
    from src.backend.config.text_source_config import Loader

    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    init = {
        "base_url": "http://old",
        "text_sources": {
            "a": {"label": "A", "loader": "local_file", "leaderboard_mode": "none"}
        },
    }
    user_config.write_text(json.dumps(init), encoding="utf-8")
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )
    config = RuntimeConfig.load_from_file(str(user_config))

    updated = {
        "base_url": "http://old",
        "text_sources": {
            "a": {"label": "A", "loader": "local_file", "leaderboard_mode": "none"},
            "b": {
                "label": "B",
                "loader": "local_file",
                "leaderboard_mode": "none",
                "local_path": "/new.txt",
            },
        },
    }
    user_config.write_text(json.dumps(updated), encoding="utf-8")

    config.reload()
    assert "b" in config.text_source_config.sources
    assert config.get_text_source("b") is not None
    assert config.get_text_source("b").loader == Loader.LOCAL_FILE


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


def test_infer_source_type_backward_compat():
    """Legacy configs without source_type round-trip without error."""
    from src.backend.config.text_source_config import (
        LeaderboardMode,
        Loader,
    )

    config = RuntimeConfig._from_dict(
        {
            "text_sources": {
                "no_path": {"label": "No Path"},
                "with_path": {"label": "With Path", "local_path": "/tmp/x.txt"},
                "with_ranking": {
                    "label": "Ranking",
                    "local_path": "/tmp/y.txt",
                    "has_ranking": True,
                },
            },
        }
    )

    no_path = config.get_text_source("no_path")
    assert no_path is not None
    assert no_path.loader == Loader.REMOTE_API
    assert no_path.leaderboard_mode == LeaderboardMode.SERVER_RESOLVED

    with_path = config.get_text_source("with_path")
    assert with_path is not None
    assert with_path.loader == Loader.LOCAL_FILE
    assert with_path.leaderboard_mode == LeaderboardMode.NONE

    ranking = config.get_text_source("with_ranking")
    assert ranking is not None
    assert ranking.loader == Loader.LOCAL_FILE
    assert ranking.leaderboard_mode == LeaderboardMode.LOCAL_LOOKUP


def test_update_text_source_adds_entry(monkeypatch, tmp_path: Path):
    """update_text_source() creates an entry in memory and persists to file."""
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

    from src.backend.config.text_source_config import (
        LeaderboardMode,
        Loader,
    )

    config = RuntimeConfig.load_from_file(str(user_config))
    config.update_text_source("my_text", "我的文本", "/tmp/my.txt")

    entry = config.get_text_source("my_text")
    assert entry is not None
    assert entry.label == "我的文本"
    assert entry.local_path == "/tmp/my.txt"
    assert entry.loader == Loader.LOCAL_FILE
    assert entry.leaderboard_mode == LeaderboardMode.NONE
    assert config.default_text_source_key == "my_text"

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert "my_text" in saved["text_sources"]
    assert saved["text_sources"]["my_text"]["label"] == "我的文本"
    assert saved["text_sources"]["my_text"]["loader"] == "local_file"
    assert saved["text_sources"]["my_text"]["leaderboard_mode"] == "none"


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
    # Old-style config: only base_url + text_sources, missing registry/ai/text_session
    user_config.write_text(
        json.dumps({"base_url": "http://old", "text_sources": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: user_config,
    )

    RuntimeConfig.ensure_user_config_exists()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["base_url"] == "http://old"
    assert saved["text_sources"] == {}
    assert "registry" in saved
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
    assert saved["base_url"] == "http://custom"
    assert saved["ai"]["provider"] == "custom"
    assert saved["ai"]["base_url"] == "http://ai.test"


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
    config.update_base_url("http://changed")

    assert json.loads(explicit_config.read_text(encoding="utf-8"))["base_url"] == (
        "http://changed"
    )
    assert json.loads(user_config.read_text(encoding="utf-8"))["base_url"] == (
        "http://user"
    )


def test_rinui_ui_save_does_not_roll_back_runtime_urls(tmp_path: Path):
    """RinUI exit-time UI save must not overwrite URLs saved after RinUI loaded."""
    user_config = tmp_path / "user" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        json.dumps(
            {
                "base_url": "http://old",
                "text_sources": {},
                "registry": {"primary_url": "", "mirror_url": ""},
                "wenlai": {"base_url": "https://old.wenlai"},
                "ai": {"base_url": "https://old.ai", "model": "old-model"},
            }
        ),
        encoding="utf-8",
    )

    ui_config = AppUIConfigManager(user_config, DEFAULT_CONFIG)
    runtime_config = RuntimeConfig.load_from_file(str(user_config))
    runtime_config.update_base_url("http://new")
    runtime_config.update_registry_url(
        primary_url="http://127.0.0.1:18888",
        mirror_url="https://mirror.example.com",
    )
    runtime_config.update_wenlai_config(base_url="https://new.wenlai")
    runtime_config.update_ai_config(base_url="https://new.ai", model="new-model")

    ui_config.config["theme"]["current_theme"] = "Dark"
    ui_config.save_config()

    saved = json.loads(user_config.read_text(encoding="utf-8"))
    assert saved["base_url"] == "http://new"
    assert saved["registry"]["primary_url"] == "http://127.0.0.1:18888"
    assert saved["registry"]["mirror_url"] == "https://mirror.example.com"
    assert saved["wenlai"]["base_url"] == "https://new.wenlai"
    assert saved["ai"]["base_url"] == "https://new.ai"
    assert saved["ai"]["model"] == "new-model"
    assert saved["ui"]["theme"]["current_theme"] == "Dark"


# ---------------------------------------------------------------------------
# OTT Repo 控制面：SourceReposConfig + 旧配置迁移
# ---------------------------------------------------------------------------


def test_source_repos_default_empty():
    config = RuntimeConfig()
    assert config.source_repos.repos == []
    assert config.source_repos.enabled_repos == []


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


def test_migration_from_old_registry_primary_url(tmp_path):
    """旧 registry.primary_url 在加载时自动迁移为一条 source_repo 订阅。"""
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
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].url == "https://cdn.example.com/old"
    assert config.source_repos.repos[0].refresh_ttl_seconds == 7200


def test_no_migration_when_source_repos_present(tmp_path):
    """已存在 source_repos 时不做迁移，避免覆盖用户数据。"""
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


def test_source_repos_serialization_roundtrip(tmp_path):
    config = RuntimeConfig()
    config.add_source_repo("https://example.org/ott-repo.json")
    config.set_source_repo_trust("https://example.org/ott-repo.json", "verified", "ed25519:abc")
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
