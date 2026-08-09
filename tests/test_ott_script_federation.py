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
    _script_authority,
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
        "mirrors": [
            {"url": "https://script-test.example.org/ott-repo.json", "priority": 1}
        ],
        "sources": [
            {
                "type": "ott-script",
                "url": "https://example.com/scripts/fetch_text.py",
                "label": "示例脚本",
                "tags": ["test"],
            }
        ],
    }


def _federation_with_script(tmp_path, *, trust_state: str = "verified"):
    config = MagicMock(spec=RuntimeConfig)
    config.registry = RegistryConfig(
        cache_ttl_seconds=3600, max_content_bytes=1_048_576
    )

    repo_entry = SourceRepoEntry(
        url="https://script-test.example.org/ott-repo.json",
        enabled=True,
        trust_state=trust_state,
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


def test_script_skipped_when_repo_not_verified(tmp_path):
    provider = _federation_with_script(tmp_path, trust_state="unverified")
    clients = provider._build_clients()
    assert not any(key.startswith("script:") for key in clients)


def test_script_skipped_when_repo_pending(tmp_path):
    """TOFU pending 仓库跳过 L3 脚本（trust_state 仅对 L3 是门禁）。"""
    provider = _federation_with_script(tmp_path, trust_state="pending")
    clients = provider._build_clients()
    assert not any(key.startswith("script:") for key in clients)


def test_script_built_when_repo_verified(tmp_path):
    provider = _federation_with_script(tmp_path, trust_state="verified")
    clients = provider._build_clients()
    assert any(key.startswith("script:") for key in clients)


class TestScriptClient:
    def test_produces_entries(self, tmp_path) -> None:
        script_source = (
            "def fetch_entries():\n"
            '    return [{"title": "S1", '
            '"content": "ScriptContent"}]\n'
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
        assert entries[0]["authority"] == _script_authority(
            "https://example.com/scripts/fetch.py"
        )

    def test_authority_namespaced_by_url(self, tmp_path) -> None:
        """不同 URL 的脚本 authority 不同，防同 entry_id 跨脚本串用。"""
        script_source = (
            'def fetch_entries():\n    return [{"title": "S1", "content": "C"}]\n'
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
        a = _ScriptClient(
            url="https://example.com/scripts/a.py",
            label="A",
            script_cache=cache,
            sandbox=sandbox,
        )
        b = _ScriptClient(
            url="https://example.com/scripts/b.py",
            label="B",
            script_cache=cache,
            sandbox=sandbox,
        )
        assert a.authority != b.authority
        assert a.authority == _script_authority("https://example.com/scripts/a.py")
        entries = a.list_entries()
        assert entries is not None
        assert entries[0]["_authority"] == a.authority

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
        script_clients = {
            k: v for k, v in clients.items() if isinstance(v, _ScriptClient)
        }
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
                "source_key": "script",
                "source_label": "示例脚本",
                "current_revision_id": "v1",
                "content_mode": "inline",
            }
        ]
        with patch.object(_ScriptClient, "list_entries", return_value=mock_entries):
            entries = provider.list_all_entries()

        script_entries = [
            e for e in entries if str(e.get("authority", "")).startswith("script:")
        ]
        assert len(script_entries) >= 1
        assert script_entries[0]["title"] == "FromScript"
        # list_all_entries 为未标 authority 的脚本条目填充命名空间化 authority
        assert script_entries[0]["authority"] == script_entries[0]["_authority"]
