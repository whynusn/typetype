"""OTT Repo _ScriptClient 联邦集成测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from src.backend.integration import ott_script_runner as runner
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
    response.iter_text.return_value = iter([text])
    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value = response
    stream_ctx.__exit__.return_value = False
    client.stream.return_value = stream_ctx
    return client


def _script_manifest(permissions=None, rights=None):
    source = {
        "type": "ott-script",
        "url": "https://example.com/scripts/fetch_text.py",
        "label": "示例脚本",
        "tags": ["test"],
    }
    if permissions is not None:
        source["permissions"] = permissions
    if rights is not None:
        source["rights"] = rights
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "script-test.example.org",
        "name": "Script Test Repo",
        "mirrors": [
            {"url": "https://script-test.example.org/ott-repo.json", "priority": 1}
        ],
        "sources": [source],
    }


def _federation_with_script(
    tmp_path, *, trust_state: str = "verified", permissions=None, rights=None
):
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
        http_client=_mock_http(_script_manifest(permissions, rights)),
        async_executor=None,
    )
    # 预写缓存，避免网络请求（mock 在 test 环境下行为不一致）
    from src.backend.integration.ott_repo_manifest import repo_cache_key

    cache_key = repo_cache_key(repo_entry.url)
    manifest_cache._write_cache(cache_key, _script_manifest(permissions, rights))

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


class TestClientsSignatureTrustState:
    """_clients_signature 必须含 trust_state：信任降级后 clients 重建。"""

    def test_signature_differs_when_trust_state_changes(self, tmp_path) -> None:
        """同 url/enabled/mtime 下仅 trust_state 不同 → 签名不同。"""
        provider = _federation_with_script(tmp_path, trust_state="verified")
        sig_verified = provider._clients_signature()
        provider._runtime_config.source_repos.repos[0].trust_state = "pending"
        sig_pending = provider._clients_signature()
        assert sig_verified != sig_pending

    def test_downgrade_rebuilds_clients_without_scripts(self, tmp_path) -> None:
        """verified → pending 降级（公钥轮换/revocation）触发重建，L3 客户端被剔除。"""
        provider = _federation_with_script(tmp_path, trust_state="verified")
        clients = provider._build_clients()
        assert any(key.startswith("script:") for key in clients)
        # 同 url/enabled/mtime，仅信任降级
        provider._runtime_config.source_repos.repos[0].trust_state = "pending"
        clients = provider._build_clients()
        assert not any(key.startswith("script:") for key in clients)


class TestScriptClient:
    @pytest.mark.skipif(
        not (runner.landlock_available() or runner.seccomp_available()),
        reason="需要 Landlock 或 seccomp 沙箱",
    )
    def test_produces_entries(self, tmp_path) -> None:
        script_source = (
            "def fetch_entries():\n"
            '    return [{"title": "S1", '
            '"content": "ScriptContent"}]\n'
        )
        mock_http = _mock_http(text=script_source)

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

    @pytest.mark.skipif(
        not (runner.landlock_available() or runner.seccomp_available()),
        reason="需要 Landlock 或 seccomp 沙箱",
    )
    def test_authority_namespaced_by_url(self, tmp_path) -> None:
        """不同 URL 的脚本 authority 不同，防同 entry_id 跨脚本串用。"""
        script_source = (
            'def fetch_entries():\n    return [{"title": "S1", "content": "C"}]\n'
        )
        mock_http = _mock_http(text=script_source)

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
        mock_http.stream.side_effect = httpx.ConnectError("offline")

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


# ── 凭据注入（ADR-011 Phase 5.4）───────────────────────────────────────


class _FakeTokenStore:
    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        self._tokens = dict(tokens or {})

    def get_token(self, key: str) -> str | None:
        return self._tokens.get(key)


class TestScriptClientSecrets:
    @pytest.mark.skipif(
        not (runner.landlock_available() or runner.seccomp_available()),
        reason="需要 Landlock 或 seccomp 沙箱",
    )
    def test_propagates_declared_secret_names(self, tmp_path) -> None:
        """secret_names 从 manifest 透传到 _ScriptClient，再注入沙箱。"""
        script_source = (
            "def fetch_entries():\n"
            '    return [{"title": "S", "content": sandbox.get_secret("k")}]\n'
        )
        mock_http = _mock_http(text=script_source)

        cache = ScriptCache(tmp_path / "scripts", mock_http)
        sandbox = ScriptSandbox(token_store=_FakeTokenStore({"k": "secret-value"}))
        client = _ScriptClient(
            url="https://example.com/scripts/fetch.py",
            label="示例脚本",
            script_cache=cache,
            sandbox=sandbox,
            secret_names=["k"],
        )
        entries = client.list_entries()
        assert entries is not None
        assert entries[0]["content"] == "secret-value"

    def test_no_secret_names_when_permissions_absent(self, tmp_path) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        cache = ScriptCache(tmp_path / "scripts", mock_http)
        client = _ScriptClient(
            url="https://example.com/scripts/fetch.py",
            label="示例脚本",
            script_cache=cache,
            sandbox=ScriptSandbox(),
        )
        assert client._secret_names == []


class TestFederationSecrets:
    def test_script_client_receives_permissions_secrets(self, tmp_path) -> None:
        provider = _federation_with_script(
            tmp_path, permissions={"secrets": ["api_key", "token"]}
        )
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert len(script_clients) == 1
        assert script_clients[0]._secret_names == ["api_key", "token"]

    def test_no_secrets_when_permissions_absent(self, tmp_path) -> None:
        provider = _federation_with_script(tmp_path)
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert script_clients[0]._secret_names == []


class TestFederationNetworkAndRights:
    def test_script_client_receives_network_allowlist(self, tmp_path) -> None:
        provider = _federation_with_script(
            tmp_path, permissions={"network": ["api.example.com"], "secrets": []}
        )
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert len(script_clients) == 1
        assert script_clients[0]._network_allowlist == ["api.example.com"]

    def test_no_network_allowlist_when_absent(self, tmp_path) -> None:
        provider = _federation_with_script(tmp_path)
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert script_clients[0]._network_allowlist == []

    def test_script_client_receives_api_level(self, tmp_path) -> None:
        provider = _federation_with_script(tmp_path, rights={"min_api_level": 2})
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert script_clients[0]._min_api_level == 2

    def test_no_api_level_when_rights_absent(self, tmp_path) -> None:
        provider = _federation_with_script(tmp_path)
        clients = provider._build_clients()
        script_clients = [c for c in clients.values() if isinstance(c, _ScriptClient)]
        assert script_clients[0]._min_api_level is None
