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
    source = config2.get_text_source("registry_test")
    assert source is not None
    assert source.loader == Loader.REGISTRY
    assert source.leaderboard_mode == (LeaderboardMode.SERVER_RESOLVED)


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
    source = config.get_text_source("b")
    assert source is not None
    assert source.loader == Loader.LOCAL_FILE


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


def test_update_registry_url_syncs_source_repo_subscription(tmp_path):
    """设置 Registry URL 必须同步落 source_repos 订阅，重启后地址不丢失。"""
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="http://127.0.0.1:18888")

    assert config.registry.primary_url == "http://127.0.0.1:18888"
    assert [r.url for r in config.source_repos.repos] == ["http://127.0.0.1:18888"]
    # 重新加载模拟重启：primary_url 与订阅一致 → 保留（不回空白）
    config2 = RuntimeConfig.load_from_file(str(path))
    assert config2.registry.primary_url == "http://127.0.0.1:18888"
    assert [r.url for r in config2.source_repos.repos] == ["http://127.0.0.1:18888"]


def test_update_registry_url_legacy_state_clear_removes_subscription(tmp_path):
    """升级态（旧代码产出 primary_url="" + 订阅在）清空时必须移除旧主订阅。

    bridge.registryPrimaryUrl 显示该订阅，old_primary 同源回退到首个
    enabled 订阅 → 清空字段必须删订阅，否则僵尸订阅残留（reviewer R1）。
    """
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="")

    assert config.source_repos.repos == []
    assert config.registry.primary_url == ""
    # 重启后不复活
    config2 = RuntimeConfig.load_from_file(str(path))
    assert config2.source_repos.repos == []


def test_update_registry_url_legacy_state_change_removes_old_subscription(
    tmp_path,
):
    """升级态换地址必须移除旧主订阅，只留新地址（reviewer R1）。"""
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="https://b.org/repo.json")

    assert [r.url for r in config.source_repos.repos] == ["https://b.org/repo.json"]
    config2 = RuntimeConfig.load_from_file(str(path))
    assert [r.url for r in config2.source_repos.repos] == ["https://b.org/repo.json"]


def test_update_registry_url_after_panel_add_clear_and_change(tmp_path):
    """面板添加订阅后清空/换地址仍能移除旧主订阅（reviewer R1 自达路径）。

    设 A → 清空 → 面板加 B → 再清空/换地址：old_primary 同源回退到
    首个 enabled 订阅（此时为 B）→ 必须正确移除。
    """
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
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


def test_update_registry_url_mirror_only_keeps_subscriptions(tmp_path):
    """仅改镜像（mirror-only）不得触碰订阅：禁用不被复活、删除不被重建。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    config.set_source_repo_enabled("https://a.org/repo.json", False)

    # 仅改镜像 → 禁用的订阅保持禁用
    config.update_registry_url(mirror_url="http://mirror.example.org/m.json")
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is False
    assert config.registry.mirror_url == "http://mirror.example.org/m.json"

    # 删除订阅后再改镜像 → 不重建
    config.remove_source_repo("https://a.org/repo.json")
    config.update_registry_url(mirror_url="http://mirror2.example.org/m.json")
    assert config.source_repos.repos == []


def test_update_registry_url_whitespace_primary_does_not_create_empty_sub(
    tmp_path,
):
    """纯空格 primary_url 不得写入空 url 订阅（直接 API 调用场景）。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="   ")

    assert config.registry.primary_url == ""
    assert config.source_repos.repos == []


def test_update_registry_url_same_primary_keep_disabled_subscription(tmp_path):
    """同值重应用（primary 非空且未变，如仅改镜像）不得复活禁用订阅。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    config.set_source_repo_enabled("https://a.org/repo.json", False)

    # 设置页同值"应用"（仅改镜像）：primary 未变，订阅保持 disabled
    config.update_registry_url(
        primary_url="https://a.org/repo.json",
        mirror_url="http://mirror.example.org/m.json",
    )
    assert config.registry.mirror_url == "http://mirror.example.org/m.json"
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is False

    # 纯同值重应用（primary + mirror 都未变）：订阅仍保持 disabled
    config.update_registry_url(primary_url="https://a.org/repo.json")
    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is False


def test_remove_source_repo_clears_matching_primary(tmp_path):
    """删除 primary_url 对应订阅时同步清空 primary_url，防止重启迁移复活。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.remove_source_repo("https://a.org/repo.json")

    assert config.source_repos.repos == []
    assert config.registry.primary_url == ""
    # 重启：primary 已清空，_from_dict 迁移不复活该订阅
    config2 = RuntimeConfig.load_from_file(str(path))
    assert config2.source_repos.repos == []
    assert config2.registry.primary_url == ""


def test_update_registry_url_reuses_existing_subscription(tmp_path):
    """重复设置同一 URL 不产生重复订阅（add_source_repo 去重）。"""
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": False}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="https://a.org/repo.json")
    config.update_registry_url(primary_url="https://a.org/repo.json")

    assert len(config.source_repos.repos) == 1
    assert config.source_repos.repos[0].enabled is True


def test_update_registry_url_clear_removes_subscription(tmp_path):
    """清空 Registry URL（设置页语义"留空则禁用"）必须移除对应订阅。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    # 清空 → 旧 primary 订阅移除，无僵尸订阅
    config.update_registry_url(primary_url="")
    assert config.source_repos.repos == []
    assert config.registry.primary_url == ""


def test_update_registry_url_change_removes_old_subscription(tmp_path):
    """更换 Registry URL 必须移除旧 primary 对应订阅，避免僵尸订阅。"""
    cfg = {
        "registry": {"primary_url": "https://a.org/repo.json", "mirror_url": ""},
        "source_repos": [{"url": "https://a.org/repo.json", "enabled": True}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))

    config.update_registry_url(primary_url="https://b.org/repo.json")

    assert [r.url for r in config.source_repos.repos] == ["https://b.org/repo.json"]
    assert config.registry.primary_url == "https://b.org/repo.json"

    # 模拟重启：primary_url 与订阅一致 → 保留，订阅仅剩新地址
    config2 = RuntimeConfig.load_from_file(str(path))
    assert config2.registry.primary_url == "https://b.org/repo.json"
    assert [r.url for r in config2.source_repos.repos] == ["https://b.org/repo.json"]


def test_load_does_not_auto_subscribe_when_empty(tmp_path):
    """0.A7：空订阅配置加载后不自动订阅任何远程源，订阅必须用户显式添加。"""
    cfg = {
        "registry": {"primary_url": "", "mirror_url": ""},
        "source_repos": [],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert config.source_repos.repos == []


def test_load_cleans_example_org_placeholder(tmp_path):
    """0.A7：加载时仅清理 example.org 占位订阅，不清用户真实订阅。"""
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


def test_registry_scripts_enabled_default_follows_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    cfg = RuntimeConfig()
    assert cfg.registry.scripts_enabled is True


def test_registry_scripts_enabled_default_disabled_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    cfg = RuntimeConfig()
    assert cfg.registry.scripts_enabled is False


def test_registry_scripts_enabled_from_dict():
    cfg_false = RuntimeConfig._from_dict({"registry": {"scripts_enabled": False}})
    assert cfg_false.registry.scripts_enabled is False
    cfg_str = RuntimeConfig._from_dict({"registry": {"scripts_enabled": "false"}})
    assert cfg_str.registry.scripts_enabled is False
    cfg_default = RuntimeConfig._from_dict({})
    assert cfg_default.registry.scripts_enabled == (sys.platform != "win32")


def test_registry_scripts_enabled_to_dict_round_trip():
    cfg = RuntimeConfig()
    cfg.registry.scripts_enabled = False
    data = cfg._to_dict()
    assert data["registry"]["scripts_enabled"] is False
    reloaded = RuntimeConfig._from_dict(data)
    assert reloaded.registry.scripts_enabled is False
