"""内置默认文本源：接线、合规与端到端加载测试。"""

import hashlib
import json
import re
from pathlib import Path

import httpx
import pytest

from src.backend.config.app_paths import builtin_ott_repo_dir, builtin_ott_repo_url
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.integration.ott_federation_provider import OttFederationProvider
from src.backend.integration.ott_repo_manifest import (
    RepoManifestCache,
    validate_repo_manifest,
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_REPO_DIRS = [
    builtin_ott_repo_dir(),
    Path(__file__).resolve().parents[1] / "public-ott-repo",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fresh_config_seeds_builtin_repo(tmp_path):
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    assert len(config.source_repos.repos) == 1
    repo = config.source_repos.repos[0]
    assert repo.url == builtin_ott_repo_url()
    assert repo.enabled


def test_explicit_empty_source_repos_not_reseeded(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"source_repos": []}), encoding="utf-8")
    config = RuntimeConfig.load_from_file(str(path))
    assert config.source_repos.repos == []


def test_setting_remote_primary_keeps_builtin(tmp_path):
    config = RuntimeConfig.load_from_file(str(tmp_path / "config.json"))
    config.update_registry_url(primary_url="https://example.org/ott-repo.json")
    urls = [r.url for r in config.source_repos.repos]
    assert builtin_ott_repo_url() in urls
    assert "https://example.org/ott-repo.json" in urls


@pytest.mark.parametrize("repo_dir", _REPO_DIRS, ids=["builtin", "public"])
def test_repo_manifest_has_no_executable_sources(repo_dir):
    manifest = _load_json(repo_dir / "ott-repo.json")
    normalized = validate_repo_manifest(manifest)
    assert normalized is not None
    assert all(s["type"] != "ott-script" for s in normalized["sources"])
    assert all(s["type"] != "ott-rule" for s in normalized["sources"])


@pytest.mark.parametrize("repo_dir", _REPO_DIRS, ids=["builtin", "public"])
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


def test_builtin_federation_loads_entries_and_detail(tmp_path):
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
