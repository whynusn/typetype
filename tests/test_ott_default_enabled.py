"""OTT Repo default_enabled 消费测试（Phase 3.4）。"""

import json
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import (
    RegistryConfig,
    RuntimeConfig,
    SourceRepoEntry,
    SourceReposConfig,
)
from src.backend.integration.ott_federation_provider import OttFederationProvider
from src.backend.integration.ott_repo_manifest import (
    RepoManifestCache,
    validate_repo_manifest,
)


def _mock_http(manifest: dict):
    client = MagicMock(spec=httpx.Client)
    text = json.dumps(manifest)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = text
    response.headers = {"content-length": str(len(text))}
    response.raise_for_status = MagicMock()
    response.json.return_value = manifest
    client.get.return_value = response
    return client


def _manifest() -> dict:
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "default-test",
        "name": "Default Test",
        "mirrors": [{"url": "https://x.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {
                "type": "ott-instance",
                "authority": "enabled-instance",
                "label": "Enabled Instance",
                "default_enabled": True,
                "endpoints": [
                    {
                        "url": "https://x.example.org/static/",
                        "profile": "static",
                        "priority": 1,
                    }
                ],
            },
            {
                "type": "ott-instance",
                "authority": "disabled-instance",
                "label": "Disabled Instance",
                "default_enabled": False,
                "endpoints": [
                    {
                        "url": "https://x.example.org/static2/",
                        "profile": "static",
                        "priority": 1,
                    }
                ],
            },
        ],
    }


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


def test_normalized_instance_preserves_default_enabled() -> None:
    normalized = validate_repo_manifest(_manifest())
    assert normalized is not None
    by_authority = {s["authority"]: s for s in normalized["sources"]}
    assert by_authority["enabled-instance"]["default_enabled"] is True
    assert by_authority["disabled-instance"]["default_enabled"] is False


def test_default_enabled_missing_defaults_to_true() -> None:
    manifest = _manifest()
    for source in manifest["sources"]:
        source.pop("default_enabled", None)
    normalized = validate_repo_manifest(manifest)
    assert normalized is not None
    assert all(s["default_enabled"] for s in normalized["sources"])


def test_disabled_instance_not_built(tmp_path) -> None:
    provider = _federation(tmp_path, _manifest())
    clients = provider._build_clients()
    assert "enabled-instance" in clients
    assert "disabled-instance" not in clients


def test_ott_bridge_reported_unsupported(tmp_path) -> None:
    manifest = _manifest()
    manifest["sources"].append(
        {
            "type": "ott-bridge",
            "bridge_kind": "wenlai",
            "endpoint": "https://example.org/api",
            "label": "桥接示例",
            "requires_credentials": True,
        }
    )
    provider = _federation(tmp_path, manifest)
    clients = provider._build_clients()
    assert "enabled-instance" in clients
    repos = provider.list_repos()
    assert repos[0]["unsupported_sources"] == ["桥接示例"]
