"""OTT Repo _ScriptClient 联邦集成测试。"""

from __future__ import annotations

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
    OttFederationProvider,
    _ScriptClient,
)
from src.backend.integration.ott_repo_manifest import RepoManifestCache
from src.backend.integration.ott_script_client import ScriptCache, ScriptSandbox


def _mock_http(json_data=None, text=""):
    client = MagicMock(spec=httpx.Client)
    if json_data is not None:
        text = json.dumps(json_data)

    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = text
    response.headers = {"content-length": str(len(text))}
    response.raise_for_status = MagicMock()
    client.get.return_value = response
    return client


def _script_manifest():
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "script-test.example.org",
        "name": "Script Test Repo",
        "mirrors": [{"url": "https://script-test.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {
                "type": "ott-script",
                "url": "https://example.com/scripts/fetch_text.py",
                "label": "示例脚本",
                "tags": ["test"],
            }
        ],
    }


def _federation_with_script(tmp_path):
    config = MagicMock(spec=RuntimeConfig)
    config.registry = MagicMock(spec=RegistryConfig)
    config.registry.cache_ttl_seconds = 3600
    config.registry.max_content_bytes = 1_048_576

    repo_entry = SourceRepoEntry(
        url="https://script-test.example.org/ott-repo.json",
        enabled=True,
    )
    config.source_repos = SourceReposConfig(repos=[repo_entry])

    cache_dir = tmp_path / "repo_manifest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_cache = RepoManifestCache(
        cache_dir=cache_dir,
        http_client=_mock_http(_script_manifest()),
        async_executor=None,
    )
    # 预写缓存，避免网络请求（mock 在 test 环境下行为不一致）
    from src.backend.integration.ott_repo_manifest import repo_cache_key
    cache_key = repo_cache_key(repo_entry.url)
    manifest_cache._write_cache(cache_key, _script_manifest())

    provider = OttFederationProvider(
        runtime_config=config,
        manifest_cache=manifest_cache,
    )
    return provider


class TestScriptClient:
    def test_produces_entries(self, tmp_path) -> None:
        script_source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"S1\", "\
            "\"content\": \"ScriptContent\"}]\n"
        )
        mock_http = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = script_source
        resp.headers = {"content-length": str(len(script_source))}
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        cache = ScriptCache(tmp_path / "scripts", mock_http)
        sandbox = ScriptSandbox()
        client = _ScriptClient(
            url="https://example.com/scripts/fetch.py",
            label="示例脚本",
            script_cache=cache,
            sandbox=sandbox,
        )
        entries = client.list_entries()
        assert entries is not None
        assert len(entries) == 1
        assert entries[0]["content"] == "ScriptContent"
        assert entries[0]["authority"] == "script"

    def test_returns_none_on_download_failure(self, tmp_path) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = httpx.ConnectError("offline")

        cache = ScriptCache(tmp_path / "scripts", mock_http)
        sandbox = ScriptSandbox()
        client = _ScriptClient(
            url="https://example.com/scripts/fetch.py",
            label="示例脚本",
            script_cache=cache,
            sandbox=sandbox,
        )
        assert client.list_entries() is None


class TestFederationWithScripts:
    def test_build_clients_creates_script_client(self, tmp_path) -> None:
        provider = _federation_with_script(tmp_path)
        clients = provider._build_clients()
        script_clients = {k: v for k, v in clients.items() if isinstance(v, _ScriptClient)}
        assert len(script_clients) == 1

    def test_list_all_entries_includes_script(self, tmp_path) -> None:
        """patch _ScriptClient.list_entries 直接返回 mock 条目。"""
        provider = _federation_with_script(tmp_path)
        from unittest.mock import patch

        mock_entries = [
            {
                "entry_id": "script-entry-1",
                "title": "FromScript",
                "content": "ScriptEntry",
                "char_count": 11,
                "authority": "script",
                "source_key": "script",
                "source_label": "示例脚本",
                "current_revision_id": "v1",
                "content_mode": "inline",
            }
        ]
        with patch.object(_ScriptClient, "list_entries", return_value=mock_entries):
            entries = provider.list_all_entries()

        script_entries = [e for e in entries if e.get("authority") == "script"]
        assert len(script_entries) >= 1
        assert script_entries[0]["title"] == "FromScript"
