"""OTT Repo 联邦聚合层桥接源（ott-bridge）集成测试。

覆盖：
- _BridgeClient 单条 / entries 列表响应归一化
- entry_id 缺省时 content hash 派生
- 非 http(s) endpoint / 非 object 响应 / 空 content 拒绝
- 未知 bridge_kind 跳过
- federation 全链路：bridge 源被构建为 _BridgeClient、authority 指纹命名、条目聚合
"""

from __future__ import annotations

import hashlib
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
    _BridgeClient,
    OttFederationProvider,
)
from src.backend.integration.ott_normalization import _bridge_authority
from src.backend.integration.ott_repo_manifest import RepoManifestCache


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _mock_http(json_data):
    client = MagicMock(spec=httpx.Client)
    text = json.dumps(json_data)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = text
    response.headers = {"content-length": str(len(text))}
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data
    client.get.return_value = response
    client.post.return_value = response
    return client


def _bridge_manifest(
    bridge_kind="generic-http", endpoint="https://bridge.example.com/api"
):
    return {
        "protocol": "ott-repo",
        "version": "1.1",
        "type": "repository",
        "repo_id": "bridge-test.example.org",
        "name": "Bridge Test Repo",
        "mirrors": [
            {"url": "https://bridge-test.example.org/ott-repo.json", "priority": 1}
        ],
        "sources": [
            {
                "type": "ott-bridge",
                "bridge_kind": bridge_kind,
                "endpoint": endpoint,
                "label": "Test Bridge",
                "requires_credentials": False,
                "tags": ["test"],
            }
        ],
    }


def _federation_with_bridge(
    tmp_path,
    bridge_kind="generic-http",
    endpoint="https://bridge.example.com/api",
    bridge_data=None,
):
    """创建一个带 bridge 订阅的 OttFederationProvider。"""
    config = MagicMock(spec=RuntimeConfig)
    config.registry = RegistryConfig(
        cache_ttl_seconds=3600, max_content_bytes=1_048_576
    )

    repo_entry = SourceRepoEntry(
        url="https://bridge-test.example.org/ott-repo.json",
        enabled=True,
    )
    config.source_repos = SourceReposConfig(repos=[repo_entry])

    manifest = _bridge_manifest(bridge_kind, endpoint)
    cache_dir = tmp_path / "repo_manifest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_cache = RepoManifestCache(
        cache_dir=cache_dir,
        http_client=_mock_http(manifest),
        async_executor=None,
    )

    bridge_http = _mock_http(bridge_data if bridge_data is not None else {})
    provider = OttFederationProvider(
        runtime_config=config,
        manifest_cache=manifest_cache,
    )
    # 注入共享 http client（_mock_http 的 client）
    provider._shared_client = bridge_http
    return provider, bridge_http


# ---------------------------------------------------------------------------
# _BridgeClient
# ---------------------------------------------------------------------------


class TestBridgeClient:
    def test_single_entry_normalized(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http({"title": "T1", "content": "正文内容"}),
        )
        entries = client.list_entries()
        assert entries is not None
        assert len(entries) == 1
        assert entries[0]["content"] == "正文内容"
        assert entries[0]["title"] == "T1"
        assert entries[0]["content_mode"] == "inline"
        assert entries[0]["authority"] == _bridge_authority(
            "https://bridge.example.com/api"
        )

    def test_entries_list_normalized(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http(
                {"entries": [{"title": "A", "content": "aaa"}, {"content": "bbb"}]}
            ),
        )
        entries = client.list_entries()
        assert entries is not None
        assert len(entries) == 2
        assert entries[0]["title"] == "A"
        assert entries[1]["content"] == "bbb"

    def test_entry_id_derived_from_content_when_missing(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http({"content": "同一内容"}),
        )
        entries = client.list_entries()
        assert entries is not None
        expected = (
            "bridge:" + hashlib.sha256("同一内容".encode("utf-8")).hexdigest()[:16]
        )
        assert entries[0]["entry_id"] == expected

    def test_empty_content_skipped(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http({"content": ""}),
        )
        assert client.list_entries() == []

    def test_non_object_response_rejected(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http([1, 2, 3]),
        )
        assert client.list_entries() is None

    def test_unknown_bridge_kind_skipped(self) -> None:
        client = _BridgeClient(
            bridge_kind="wenlai",
            endpoint="https://bridge.example.com/api",
            label="Test Bridge",
            http_client=_mock_http({"content": "x"}),
        )
        assert client.list_entries() is None

    def test_non_http_endpoint_rejected(self) -> None:
        client = _BridgeClient(
            bridge_kind="generic-http",
            endpoint="file:///etc/passwd",
            label="Test Bridge",
            http_client=_mock_http({"content": "x"}),
        )
        assert client.list_entries() is None


# ---------------------------------------------------------------------------
# federation 全链路
# ---------------------------------------------------------------------------


class TestBridgeFederation:
    def test_bridge_source_built_into_clients(self, tmp_path) -> None:
        provider, _ = _federation_with_bridge(
            tmp_path,
            bridge_data={"title": "T", "content": "来自桥的内容"},
        )
        clients = provider._build_clients()
        authority = _bridge_authority("https://bridge.example.com/api")
        assert authority in clients
        assert isinstance(clients[authority], _BridgeClient)

    def test_list_all_entries_includes_bridge(self, tmp_path) -> None:
        provider, _ = _federation_with_bridge(
            tmp_path,
            bridge_data={"title": "T", "content": "来自桥的内容"},
        )
        entries = provider.list_all_entries()
        assert len(entries) == 1
        assert entries[0]["content"] == "来自桥的内容"
        assert entries[0]["_authority"] == _bridge_authority(
            "https://bridge.example.com/api"
        )

    def test_bridge_entry_inline_typing_path(self, tmp_path) -> None:
        """桥条目 content_mode=inline → 走 loadFederatedInlineEntry 打字路径。"""
        provider, _ = _federation_with_bridge(
            tmp_path,
            bridge_data={"title": "T", "content": "桥接文本"},
        )
        entries = provider.list_all_entries()
        assert entries[0]["content_mode"] == "inline"
        # inline 条目按契约通过 get_entry(authority, entry_id) 取正文
        entry = provider.get_entry(entries[0]["_authority"], entries[0]["entry_id"])
        assert entry is not None
        assert entry["content"] == "桥接文本"
