"""OTT Repo 联邦聚合层规则源集成测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx

from src.backend.config.runtime_config import (
    RegistryConfig,
    RuntimeConfig,
    SourceRepoEntry,
    SourceReposConfig,
)
from src.backend.integration.ott_federation_provider import (
    OttFederationProvider,
    _RuleClient,
)
from src.backend.integration.ott_repo_manifest import RepoManifestCache
from src.backend.integration.ott_rule_interpreter import OttRuleInterpreter


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _mock_http(json_data=None, text=""):
    client = MagicMock(spec=httpx.Client)
    if json_data is not None:
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


def _rule_manifest():
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "rule-test.example.org",
        "name": "Rule Test Repo",
        "mirrors": [
            {"url": "https://rule-test.example.org/ott-repo.json", "priority": 1}
        ],
        "sources": [
            {
                "type": "ott-rule",
                "rule_id": "sample-rule",
                "label": "Sample Rule",
                "rule": {
                    "request": {
                        "url": "https://example.com/api?page={page}",
                        "method": "GET",
                    },
                    "extract": {"title": "$.title", "content": "$.content"},
                    "transform": [],
                    "pagination": {
                        "param": "page",
                        "start": 1,
                        "step": 1,
                        "max_pages": 3,
                    },
                },
                "tags": ["test"],
            }
        ],
    }


def _federation_with_rule(tmp_path):
    """创建一个带规则订阅的 OttFederationProvider。"""
    config = MagicMock(spec=RuntimeConfig)
    config.registry = RegistryConfig(
        cache_ttl_seconds=3600, max_content_bytes=1_048_576
    )

    repo_entry = SourceRepoEntry(
        url="https://rule-test.example.org/ott-repo.json",
        enabled=True,
    )
    config.source_repos = SourceReposConfig(repos=[repo_entry])

    # 预写 manifest 缓存，跳过网络
    cache_dir = tmp_path / "repo_manifest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_cache = RepoManifestCache(
        cache_dir=cache_dir,
        http_client=_mock_http(_rule_manifest()),
        async_executor=None,
    )

    provider = OttFederationProvider(
        runtime_config=config,
        manifest_cache=manifest_cache,
    )
    return provider


# ---------------------------------------------------------------------------
# _RuleClient
# ---------------------------------------------------------------------------


class TestRuleClient:
    def test_produces_entries(self) -> None:
        # 第一页有数据，第二页空 → 终止循环，只产 1 条
        page1 = [{"title": "T1", "content": "Content1"}]
        mock_client = MagicMock(spec=httpx.Client)

        resp1 = MagicMock(spec=httpx.Response)
        resp1.status_code = 200
        resp1.text = json.dumps(page1)
        resp1.headers = {"content-length": "100"}
        resp1.raise_for_status = MagicMock()
        resp1.iter_text = MagicMock(return_value=iter([json.dumps(page1)]))

        resp_empty = MagicMock(spec=httpx.Response)
        resp_empty.status_code = 200
        resp_empty.text = json.dumps([])
        resp_empty.headers = {"content-length": "2"}
        resp_empty.raise_for_status = MagicMock()
        resp_empty.iter_text = MagicMock(return_value=iter([json.dumps([])]))

        mock_client.get.side_effect = [resp1, resp_empty]

        interp = OttRuleInterpreter(mock_client)
        client = _RuleClient(
            rule_id="r1",
            rule={
                "request": {"url": "https://example.com/api"},
                "extract": {"title": "$.title", "content": "$.content"},
            },
            interpreter=interp,
        )
        entries = client.list_entries()
        assert entries is not None
        assert len(entries) == 1
        assert entries[0]["authority"] == "rule:r1"
        assert entries[0]["_authority"] == "rule:r1"
        assert entries[0]["title"] == "T1"

    def test_returns_empty_list_when_no_entries(self) -> None:
        interp = OttRuleInterpreter(_mock_http([]))
        client = _RuleClient(
            rule_id="r1",
            rule={
                "request": {"url": "https://example.com/api"},
                "extract": {"title": "$.title"},
            },
            interpreter=interp,
        )
        entries = client.list_entries()
        assert entries == []

    def test_returns_none_on_exception(self) -> None:
        interp = MagicMock(spec=OttRuleInterpreter)
        interp.list_entries.side_effect = RuntimeError("boom")
        client = _RuleClient(rule_id="r1", rule={}, interpreter=interp)
        assert client.list_entries() is None


# ---------------------------------------------------------------------------
# Federation aggregation
# ---------------------------------------------------------------------------


class TestFederationWithRules:
    def test_list_all_entries_includes_rule_sources(self, tmp_path) -> None:
        provider = _federation_with_rule(tmp_path)
        # mock 规则解释器的 HTTP 响应
        with patch.object(OttRuleInterpreter, "__init__", lambda self, **kw: None):
            with patch.object(
                OttRuleInterpreter,
                "list_entries",
                return_value=[
                    {
                        "entry_id": "rule-entry-1",
                        "title": "RuleTitle",
                        "content": "RuleContent",
                        "char_count": 11,
                        "authority": "rule:sample-rule",
                        "source_key": "rule:sample-rule",
                        "source_label": "Sample Rule",
                        "current_revision_id": "rev1",
                        "content_mode": "inline",
                    }
                ],
            ):
                entries = provider.list_all_entries()

        # 至少包含 rule 来源的条目
        rule_entries = [
            e for e in entries if e.get("authority", "").startswith("rule:")
        ]
        assert len(rule_entries) >= 1
        assert rule_entries[0]["title"] == "RuleTitle"

    def test_build_clients_creates_rule_client(self, tmp_path) -> None:
        provider = _federation_with_rule(tmp_path)
        clients = provider._build_clients()
        # 上游规范：rule:{repo_id}:{rule_id}
        assert "rule:rule-test.example.org:sample-rule" in clients
        assert isinstance(
            clients["rule:rule-test.example.org:sample-rule"], _RuleClient
        )

    def test_rule_authority_isolation(self, tmp_path) -> None:
        """rule authority 与 instance authority 命名空间隔离。"""
        provider = _federation_with_rule(tmp_path)
        clients = provider._build_clients()
        # 没有 instance authority，只有 rule（含 repo_id 命名空间）
        assert "rule:rule-test.example.org:sample-rule" in clients
        # 不存在裸 "sample-rule" 作为 instance authority
        assert "sample-rule" not in clients
