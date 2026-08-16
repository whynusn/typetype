"""内置默认文本源：接线、合规与端到端加载测试。"""

import hashlib
import json
import re
from pathlib import Path

import httpx
import pytest

from src.backend.config.app_paths import (
    builtin_ott_repo_dir,
    builtin_ott_repo_url,
    default_ott_hub_url,
)
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.integration.ott_federation_provider import OttFederationProvider
from src.backend.integration.ott_repo_manifest import (
    RepoManifestCache,
    validate_repo_manifest,
)
from src.backend.integration.ott_normalization import local_path_from_file_uri

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_REPO_DIRS = [builtin_ott_repo_dir()]
_REPO_IDS = ["builtin"]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _isolate_instance_cache(tmp_path, monkeypatch) -> None:
    root = tmp_path / "instance-cache"
    monkeypatch.setattr(
        OttFederationProvider,
        "_instance_cache_dir",
        lambda self, authority: (
            root / hashlib.sha256(authority.encode("utf-8")).hexdigest()[:12]
        ),
    )


def test_fresh_config_seeds_builtin_repo(tmp_path):
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    urls = [r.url for r in config.source_repos.repos]
    # 默认订阅 = 内置离线兜底 + hub（开箱即用）
    assert builtin_ott_repo_url() in urls
    assert default_ott_hub_url() in urls
    assert all(r.enabled for r in config.source_repos.repos)


def test_explicit_empty_source_repos_not_reseeded(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"source_repos": []}), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert config.source_repos.repos == []


def test_stale_only_subscription_reseeded_to_builtin(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "source_repos": [
                    {"url": "https://example.org/ott-repo.json", "enabled": True}
                ]
            }
        ),
        encoding="utf-8",
    )
    config = RuntimeConfig.load_from_file(str(path))
    urls = [r.url for r in config.source_repos.repos]
    assert urls == [builtin_ott_repo_url(), default_ott_hub_url()]


def test_setting_remote_primary_keeps_builtin(tmp_path):
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    config.update_registry_url(primary_url="https://example.org/ott-repo.json")
    urls = [r.url for r in config.source_repos.repos]
    assert builtin_ott_repo_url() in urls
    assert "https://example.org/ott-repo.json" in urls


@pytest.mark.parametrize("repo_dir", _REPO_DIRS, ids=_REPO_IDS)
def test_repo_manifest_has_no_executable_sources(repo_dir):
    manifest = _load_json(repo_dir / "ott-repo.json")
    normalized = validate_repo_manifest(manifest)
    assert normalized is not None
    assert all(s["type"] != "ott-script" for s in normalized["sources"])
    assert all(s["type"] != "ott-rule" for s in normalized["sources"])


@pytest.mark.parametrize("repo_dir", _REPO_DIRS, ids=_REPO_IDS)
def test_static_profile_summaries_and_details_compliant(repo_dir):
    sources = _load_json(repo_dir / "static" / "sources.json")["sources"]
    summaries = _load_json(repo_dir / "static" / "entries.json")["entries"]
    entries_dir = repo_dir / "static" / "entries"
    assert sources and summaries
    assert len(summaries) == len(sources)
    for summary in summaries:
        assert "content" not in summary
        assert _ID_PATTERN.fullmatch(summary["entry_id"])
        assert _ID_PATTERN.fullmatch(summary["source_key"])
        assert _ID_PATTERN.fullmatch(summary["current_revision_id"])
        detail_path = entries_dir / f"{summary['entry_id']}.json"
        assert detail_path.exists()
        detail = _load_json(detail_path)
        assert detail["content"]
        assert detail["char_count"] == len(detail["content"])
        expected_hash = (
            "sha256:" + hashlib.sha256(detail["content"].encode("utf-8")).hexdigest()
        )
        assert detail["content_hash"] == expected_hash
        assert detail["entry_id"] == summary["entry_id"]
        assert detail["source_key"] == summary["source_key"]


def test_builtin_federation_loads_entries_and_detail(tmp_path, monkeypatch):
    _isolate_instance_cache(tmp_path, monkeypatch)
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    manifest_cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=httpx.Client(timeout=10.0),
        async_executor=None,
        runtime_config=config,
    )
    federation = OttFederationProvider(config, manifest_cache)
    entries = federation.list_all_entries()
    assert len(entries) == 3
    assert all(e["authority"] == "typetype-builtin-static" for e in entries)
    detail = federation.get_entry("typetype-builtin-static", "classic_sentences")
    assert detail is not None
    assert detail["content"]


def test_builtin_federation_entries_carry_ott_instance_source_type(
    tmp_path, monkeypatch
):
    """联邦聚合必须为 instance 源条目注入 _source_type=ott-instance（refresh 策略读它）。"""
    _isolate_instance_cache(tmp_path, monkeypatch)
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    manifest_cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=httpx.Client(timeout=10.0),
        async_executor=None,
        runtime_config=config,
    )
    federation = OttFederationProvider(config, manifest_cache)
    entries = federation.list_all_entries()
    assert len(entries) == 3
    assert all(e["_source_type"] == "ott-instance" for e in entries)


def test_local_path_from_file_uri_strips_windows_drive_slash() -> None:
    path = local_path_from_file_uri("file:///D:/a/b.json")
    normalized = str(path).replace("\\", "/")
    assert normalized == "D:/a/b.json"


def test_blocked_content_hash_blocks_entry_detail(tmp_path, monkeypatch) -> None:
    _isolate_instance_cache(tmp_path, monkeypatch)
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    detail_file = (
        builtin_ott_repo_dir() / "static" / "entries" / "classic_sentences.json"
    )
    blocked_hash = _load_json(detail_file)["content_hash"]
    config.blocked_content_hashes = [blocked_hash]
    manifest_cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=httpx.Client(timeout=10.0),
        async_executor=None,
        runtime_config=config,
    )
    federation = OttFederationProvider(config, manifest_cache)
    detail = federation.get_entry("typetype-builtin-static", "classic_sentences")
    assert detail is None
