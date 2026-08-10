"""OTT Repo requires 协商测试（Phase 3.3）。"""

import json
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import (
    RegistryConfig,
    RuntimeConfig,
    SourceRepoEntry,
    SourceReposConfig,
)
from src.backend.integration.ott_federation_provider import (
    CLIENT_OTT_CORE_VERSION,
    OttFederationProvider,
    _compare_versions,
    _satisfies_ott_core,
)
from src.backend.integration.ott_repo_manifest import RepoManifestCache


def _mock_http(manifest: dict):
    client = MagicMock(spec=httpx.Client)
    text = json.dumps(manifest)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = text
    response.headers = {}
    response.raise_for_status = MagicMock()
    response.json.return_value = manifest
    client.get.return_value = response
    return client


def _federation(tmp_path, manifest: dict) -> OttFederationProvider:
    config = MagicMock(spec=RuntimeConfig)
    config.registry = RegistryConfig(
        cache_ttl_seconds=3600, max_content_bytes=1_048_576
    )
    config.source_repos = SourceReposConfig(
        repos=[SourceRepoEntry(url="https://x.example.org/ott-repo.json", enabled=True)]
    )
    cache_dir = tmp_path / "repo_manifest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_cache = RepoManifestCache(
        cache_dir=cache_dir,
        http_client=_mock_http(manifest),
        async_executor=None,
    )
    return OttFederationProvider(runtime_config=config, manifest_cache=manifest_cache)


def _manifest(requires: dict) -> dict:
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "requires-test",
        "name": "Requires Test",
        "mirrors": [{"url": "https://x.example.org/ott-repo.json", "priority": 1}],
        "requires": requires,
        "sources": [
            {
                "type": "ott-instance",
                "authority": "req-instance",
                "label": "Req Instance",
                "endpoints": [
                    {
                        "url": "https://x.example.org/static/",
                        "profile": "static",
                        "priority": 1,
                    }
                ],
            }
        ],
    }


def test_version_comparison_helpers() -> None:
    assert _compare_versions("1.0", "1.0") == 0
    assert _compare_versions("1.1", "1.0") == 1
    assert _compare_versions("1.0", "1.1") == -1
    assert _satisfies_ott_core(">=1.0", CLIENT_OTT_CORE_VERSION)
    assert _satisfies_ott_core("1.0", CLIENT_OTT_CORE_VERSION)
    assert _satisfies_ott_core("<=1.0", CLIENT_OTT_CORE_VERSION)
    assert not _satisfies_ott_core(">1.0", CLIENT_OTT_CORE_VERSION)
    assert not _satisfies_ott_core("<=0.9", CLIENT_OTT_CORE_VERSION)
    assert not _satisfies_ott_core("garbage", CLIENT_OTT_CORE_VERSION)


def test_incompatible_ott_core_skips_repo(tmp_path) -> None:
    provider = _federation(tmp_path, _manifest({"ott_core": ">=2.0"}))
    assert provider._build_clients() == {}
    repos = provider.list_repos()
    assert repos[0]["incompatible_reason"] == "需要 OTT Core >=2.0，客户端为 1.0"
    assert repos[0]["authorities"] == []


def test_missing_client_feature_skips_repo(tmp_path) -> None:
    provider = _federation(tmp_path, _manifest({"client_features": ["search"]}))
    assert provider._build_clients() == {}
    repos = provider.list_repos()
    assert repos[0]["incompatible_reason"] == "缺少客户端能力: search"


def test_compatible_repo_built_and_reason_none(tmp_path) -> None:
    provider = _federation(
        tmp_path,
        _manifest({"ott_core": ">=1.0", "client_features": ["segmented_content"]}),
    )
    clients = provider._build_clients()
    assert "req-instance" in clients
    repos = provider.list_repos()
    assert repos[0]["incompatible_reason"] is None
