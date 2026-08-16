"""OTT Repo 联邦聚合层规则源集成测试。"""

from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import MagicMock, patch

import httpx

from src.backend.config.runtime_config import (
    OttConfig,
    RuntimeConfig,
    SourceRepoEntry,
    SourceReposConfig,
)
from src.backend.integration import ott_rule_interpreter as interpreter_module
from src.backend.integration.ott_federation_provider import (
    _EntryCache,
    OttFederationProvider,
    _RuleClient,
    _ScriptClient,
    _declared_refresh_policy,
)
from src.backend.integration.ott_repo_manifest import RepoManifestCache
from src.backend.integration.ott_rule_interpreter import OttRuleInterpreter
from src.backend.integration.ott_script_client import ScriptCache, ScriptSandbox


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
    config.ott = OttConfig(cache_ttl_seconds=3600, max_content_bytes=1_048_576)

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

        # sandbox DNS 把 example.com 解析到保留段（198.18.0.0/15，is_private），
        # validate_url 会拒绝该 URL → 测试环境必须 patch 为公网 IP
        with patch.object(
            interpreter_module, "_resolve_host", return_value=["93.184.215.14"]
        ):
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
        # 契约 C2：非空 authority 时解释器负责 authority/source_key，客户端不补丁
        assert entries[0]["authority"] == "rule:r1"
        assert entries[0]["source_key"] == "rule:r1"
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


class TestScriptClientChecksum:
    def test_checksum_passed_to_script_cache(self) -> None:
        """契约 C1：checksum 非空时透传给 ScriptCache.get_script(expected_checksum=...)。"""
        cache = MagicMock(spec=ScriptCache)
        cache.get_script.return_value = "def fetch_entries():\n    return []\n"
        sandbox = MagicMock(spec=ScriptSandbox)
        sandbox.execute_strict.return_value = []
        client = _ScriptClient(
            url="https://example.com/scripts/a.py",
            label="A",
            script_cache=cache,
            sandbox=sandbox,
            checksum="sha256:" + "ab" * 32,
        )
        assert client.list_entries() == []
        cache.get_script.assert_called_once_with(
            "https://example.com/scripts/a.py",
            expected_checksum="sha256:" + "ab" * 32,
        )

    def test_no_checksum_plain_call(self) -> None:
        """checksum 为空时不传 expected_checksum（兼容 C1 落地前后的 ScriptCache）。"""
        cache = MagicMock(spec=ScriptCache)
        cache.get_script.return_value = "def fetch_entries():\n    return []\n"
        sandbox = MagicMock(spec=ScriptSandbox)
        sandbox.execute_strict.return_value = []
        client = _ScriptClient(
            url="https://example.com/scripts/a.py",
            label="A",
            script_cache=cache,
            sandbox=sandbox,
        )
        assert client.list_entries() == []
        cache.get_script.assert_called_once_with("https://example.com/scripts/a.py")

    def test_execution_failure_propagates_as_none(self) -> None:
        """脚本执行层失败（strict 返回 None）→ 源不可用，刷新统计计失败。"""
        cache = MagicMock(spec=ScriptCache)
        cache.get_script.return_value = "def fetch_entries():\n    raise RuntimeError\n"
        sandbox = MagicMock(spec=ScriptSandbox)
        sandbox.execute_strict.return_value = None
        client = _ScriptClient(
            url="https://example.com/scripts/a.py",
            label="A",
            script_cache=cache,
            sandbox=sandbox,
        )
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

    def test_list_all_entries_sets_rule_source_type(self, tmp_path) -> None:
        """联邦聚合必须为 rule 源条目注入 _source_type=ott-rule（refresh 策略读它）。"""
        provider = _federation_with_rule(tmp_path)
        with patch.object(OttRuleInterpreter, "__init__", lambda self, **kw: None):
            with patch.object(
                OttRuleInterpreter,
                "list_entries",
                return_value=[
                    {
                        "entry_id": "rule-entry-1",
                        "title": "RuleTitle",
                        "content": "RuleContent",
                    }
                ],
            ):
                entries = provider.list_all_entries()

        rule_entries = [
            e for e in entries if e.get("authority", "").startswith("rule:")
        ]
        assert len(rule_entries) >= 1
        assert rule_entries[0]["_source_type"] == "ott-rule"

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

    def test_build_clients_uses_client_api_level(self, tmp_path) -> None:
        """federation 创建的 interpreter 必须携带客户端 API level。"""
        provider = _federation_with_rule(tmp_path)
        clients = provider._build_clients()
        rule_client = clients["rule:rule-test.example.org:sample-rule"]
        assert isinstance(rule_client, _RuleClient)
        interp = rule_client._interpreter
        from src.backend.integration.ott_rule_interpreter import CLIENT_API_LEVEL

        assert interp._api_level == CLIENT_API_LEVEL
        rule = _rule_manifest()["sources"][0]["rule"]
        rule = {**rule, "rights": {"min_api_level": CLIENT_API_LEVEL + 1}}
        assert interp.list_entries(rule, "r1") == []


# ---------------------------------------------------------------------------
# Phase 3.9：客户端复用与结果 TTL 缓存
# ---------------------------------------------------------------------------


def test_clients_reused_within_signature(tmp_path):
    provider = _federation_with_rule(tmp_path)
    first = provider._build_clients()
    second = provider._build_clients()
    assert first is second
    assert provider._shared_client is not None

    provider._runtime_config.source_repos.repos[0].enabled = False
    third = provider._build_clients()
    assert third is not first
    assert third == {}


def test_rule_entries_cached_within_ttl(tmp_path):
    provider = _federation_with_rule(tmp_path)
    with patch.object(
        OttRuleInterpreter,
        "list_entries",
        return_value=[{"entry_id": "e1", "title": "T", "content": "C"}],
    ) as mock_list:
        entries1 = provider.list_all_entries()
        entries2 = provider.list_all_entries()
    assert mock_list.call_count == 1
    assert len(entries1) == 1
    assert len(entries2) == 1


def test_entry_cache_expires_after_ttl():
    cache = _EntryCache(ttl_seconds=1)
    cache.set("k", [{"entry_id": "e1"}])
    assert cache.get("k") is not None
    cache._items["k"] = (time.time() - 2, [{"entry_id": "e1"}])
    assert cache.get("k") is None


def test_entry_cache_force_skips_ttl():
    """force=True 无视 TTL 直接视为 miss（手动刷新语义）。"""
    cache = _EntryCache(ttl_seconds=3600)
    cache.set("k", [{"entry_id": "e1"}])
    assert cache.get("k") is not None
    assert cache.get("k", force=True) is None
    # force 后条目被移除，后续普通 get 也是 miss
    assert cache.get("k") is None


def test_list_all_entries_force_skips_entry_cache(tmp_path):
    """总刷新 force=True 必须绕过 rule 条目内存缓存，重新执行规则。"""
    provider = _federation_with_rule(tmp_path)
    entry = {"entry_id": "e1", "title": "T", "content": "C"}
    with patch.object(
        OttRuleInterpreter,
        "list_entries",
        return_value=[entry],
    ) as mock_list:
        provider.list_all_entries()  # 首次：物化 + 写缓存
        provider.list_all_entries()  # TTL 内命中缓存
        assert mock_list.call_count == 1
        provider.list_all_entries(force=True)  # force：绕过缓存重执行
        assert mock_list.call_count == 2


def test_rule_client_list_entries_force_bypasses_cache():
    """_RuleClient.list_entries(force=True) 缓存命中仍重执行（单源刷新路径）。"""
    interp = MagicMock(spec=OttRuleInterpreter)
    interp.list_entries.return_value = [{"entry_id": "e1"}]
    cache = _EntryCache(ttl_seconds=3600)
    client = _RuleClient(rule_id="r1", rule={}, interpreter=interp, entry_cache=cache)
    client.list_entries()
    client.list_entries()  # TTL 内命中缓存
    assert interp.list_entries.call_count == 1
    client.list_entries(force=True)
    assert interp.list_entries.call_count == 2


def test_entries_carry_repo_meta_for_dynamic_grouping(tmp_path):
    """条目携带所属订阅源元信息（_repo_*）：开源文库按订阅源动态分组（不硬编码）。

    条目物化时注入 _repo_id/_repo_name/_repo_url/_repo_max_entries——
    QML 按条目「属于哪个订阅源」归组；authorities_of_repo / repo_id_of_url
    供 repo 级刷新与删除订阅清快照使用。
    """
    provider = _federation_with_rule(tmp_path)
    entry = {"entry_id": "e1", "title": "T", "content": "C"}
    with patch.object(OttRuleInterpreter, "list_entries", return_value=[entry]):
        entries = provider.list_all_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["_repo_id"] == "rule-test.example.org"
    assert e["_repo_name"] == "Rule Test Repo"
    assert e["_repo_url"] == "https://rule-test.example.org/ott-repo.json"
    assert e["_repo_max_entries"] == 0  # manifest 未声明 → 0（无上限）
    # source 级元信息（2026-08-15）：列表精度到每条规则/源（authority 级分组）
    assert e["_authority"] == "rule:rule-test.example.org:sample-rule"
    assert e["_source_label"] == "Sample Rule"  # manifest source.label（不硬编码）
    assert e["_source_type"] == "ott-rule"

    # authority ↔ repo 反查（repo 级刷新 / 删除订阅清理快照）
    auth = "rule:rule-test.example.org:sample-rule"
    assert provider.authorities_of_repo("rule-test.example.org") == [auth]
    assert (
        provider.repo_id_of_url("https://rule-test.example.org/ott-repo.json")
        == "rule-test.example.org"
    )


def test_refresh_source_only_materializes_target_authority(tmp_path):
    """refresh_source(authority) 只重新物化该源，其他 authority 零调用。"""
    provider = _federation_with_rule(tmp_path)
    authority = "rule:rule-test.example.org:sample-rule"
    entry = {"entry_id": "e1", "title": "T", "content": "C"}
    with patch.object(
        OttRuleInterpreter,
        "list_entries",
        return_value=[entry],
    ) as mock_list:
        provider.list_all_entries()
        mock_list.call_count = 0  # 缓存已命中（provider 级 _EntryCache）
        refreshed = provider.refresh_source(authority)
    assert mock_list.call_count == 1
    assert len(refreshed) == 1
    assert refreshed[0]["_authority"] == authority
    assert refreshed[0]["_source_type"] == "ott-rule"

    # 不存在的 authority：零网络、空结果
    with patch.object(
        OttRuleInterpreter, "list_entries", return_value=[entry]
    ) as mock_list:
        assert provider.refresh_source("rule:unknown:source") == []
        mock_list.assert_not_called()


# ---------------------------------------------------------------------------
# 屏蔽过滤与 disabled 订阅
# ---------------------------------------------------------------------------


class TestSegmentBlockingAndDisabledRepos:
    def test_get_segment_blocked_hash_returns_none(self, tmp_path) -> None:
        """get_segment 对齐 get_entry：content_hash 在屏蔽清单 → None。"""
        provider = _federation_with_rule(tmp_path)
        entry_content = "Content1"
        entry = {
            "entry_id": "rule-entry-1",
            "title": "T1",
            "content": entry_content,
            "current_revision_id": "rev1",
            "content_mode": "inline",
        }
        authority = "rule:rule-test.example.org:sample-rule"
        with patch.object(OttRuleInterpreter, "list_entries", return_value=[entry]):
            seg = provider.get_segment(authority, "rule-entry-1", "rev1", 1)
        assert seg is not None
        assert seg["content"] == entry_content

        blocked_hash = (
            "sha256:" + hashlib.sha256(entry_content.encode("utf-8")).hexdigest()
        )
        provider._runtime_config.blocked_content_hashes = [blocked_hash]
        with patch.object(OttRuleInterpreter, "list_entries", return_value=[entry]):
            seg = provider.get_segment(authority, "rule-entry-1", "rev1", 1)
        assert seg is None

    def test_list_repos_disabled_repo_no_network(self, tmp_path) -> None:
        """disabled 订阅：list_repos 不拉 manifest（零网络），本地数据标注 enabled=false。"""
        provider = _federation_with_rule(tmp_path)
        provider._runtime_config.source_repos.repos[0].enabled = False
        with patch.object(provider, "_manifest_for") as mock_manifest:
            repos = provider.list_repos()
        mock_manifest.assert_not_called()
        assert len(repos) == 1
        assert repos[0]["enabled"] is False
        assert repos[0]["loaded"] is False

    def test_list_repos_enabled_repo_still_loads_manifest(self, tmp_path) -> None:
        """启用订阅保持原行为：list_repos 走 manifest 摘要。"""
        provider = _federation_with_rule(tmp_path)
        with patch.object(provider, "_manifest_for", wraps=provider._manifest_for):
            repos = provider.list_repos()
        assert len(repos) == 1
        assert repos[0]["enabled"] is True
        assert repos[0]["loaded"] is True


def test_list_all_entries_records_failed_authorities(tmp_path):
    """物化失败（异常）的 authority 记录到 last_list_failed（刷新失败反馈用）。"""
    provider = _federation_with_rule(tmp_path)
    with patch.object(
        OttRuleInterpreter, "list_entries", side_effect=RuntimeError("boom")
    ):
        entries = provider.list_all_entries()
    assert entries == []
    assert provider._last_list_ok == []
    assert provider._last_list_failed == ["rule:rule-test.example.org:sample-rule"]


def test_list_all_entries_records_none_as_failed_authority(tmp_path):
    """解释器返回 None（网络不可达）→ 该 rule 源计失败，而不是当空成功。"""
    provider = _federation_with_rule(tmp_path)
    with patch.object(OttRuleInterpreter, "list_entries", return_value=None):
        entries = provider.list_all_entries()
    assert entries == []
    assert provider._last_list_ok == []
    assert provider._last_list_failed == ["rule:rule-test.example.org:sample-rule"]


def test_list_all_entries_records_ok_authorities(tmp_path):
    """物化成功的 authority 记录到 last_list_ok（区分刷新成功与回退快照）。"""
    provider = _federation_with_rule(tmp_path)
    with patch.object(
        OttRuleInterpreter, "list_entries", return_value=[{"entry_id": "e1"}]
    ):
        entries = provider.list_all_entries()
    assert [e["entry_id"] for e in entries] == ["e1"]
    assert provider._last_list_ok == ["rule:rule-test.example.org:sample-rule"]
    assert provider._last_list_failed == []


def test_declared_refresh_policy_mapping():
    assert _declared_refresh_policy(
        {"rule": {"schedule": {"mode": "manual", "cache_ttl_seconds": 3600}}}
    ) == {"mode": "on_demand", "interval_seconds": 0}
    assert _declared_refresh_policy(
        {"refresh": {"mode": "hourly", "cache_ttl_seconds": 120}}
    ) == {"mode": "interval", "interval_seconds": 3600}
    assert _declared_refresh_policy({"rule": {"schedule": {"mode": "daily"}}}) == {
        "mode": "interval",
        "interval_seconds": 86400,
    }
    assert _declared_refresh_policy({"rule": {"schedule": {"mode": "weekly"}}}) == {
        "mode": "interval",
        "interval_seconds": 604800,
    }
    assert _declared_refresh_policy({"rule": {"schedule": {"mode": "nope"}}}) is None
    assert _declared_refresh_policy({}) is None


def test_decorate_injects_declared_refresh_policy(tmp_path):
    """manifest 声明的 refresh/schedule 注入条目，catalog 据此生成策略。"""
    from src.backend.application.services.snapshot_catalog_service import (
        SnapshotCatalogService,
    )
    from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
    from src.backend.integration.refresh_policy import MODE_INTERVAL, RefreshPolicy

    provider = _federation_with_rule(tmp_path)
    manifest = _rule_manifest()
    manifest["sources"][0]["rule"]["schedule"] = {"mode": "daily"}
    with patch.object(provider, "_manifest_for", return_value=manifest):
        with patch.object(
            OttRuleInterpreter, "list_entries", return_value=[{"entry_id": "e1"}]
        ):
            entries = provider.list_all_entries()
    assert entries[0]["_refresh_policy"]["mode"] == "interval"
    assert entries[0]["_refresh_policy"]["interval_seconds"] == 86400

    store = EntrySnapshotStore(tmp_path / "snapshots")
    service = SnapshotCatalogService(provider, store, None)
    policy = service._policy_for(entries[0])
    assert policy == RefreshPolicy(MODE_INTERVAL, 86400)


def test_preview_manifest_returns_directory_references(tmp_path):
    """添加订阅弹窗可预览 directory，列出 repository-ref 供显式添加。"""
    provider = _federation_with_rule(tmp_path)
    directory = {
        "protocol": "ott-repo",
        "version": "1.1",
        "type": "directory",
        "repo_id": "directory.example.org",
        "name": "社区目录",
        "mirrors": [{"url": "https://dir.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {
                "type": "repository-ref",
                "url": "https://texts.example.org/ott-repo.json",
                "label": "示例文库",
                "tags": ["chinese"],
            }
        ],
    }
    with patch.object(provider, "_manifest_for", return_value=directory):
        preview = provider.preview_manifest("https://dir.example.org/ott-repo.json")
    assert preview["type"] == "directory"
    assert preview["error"] == ""
    assert preview["repositories"][0]["label"] == "示例文库"
    assert (
        preview["repositories"][0]["url"] == "https://texts.example.org/ott-repo.json"
    )


def test_preview_manifest_failure_returns_error(tmp_path):
    provider = _federation_with_rule(tmp_path)
    with patch.object(provider, "_manifest_for", return_value=None):
        preview = provider.preview_manifest("https://down.example.org/ott-repo.json")
    assert preview["error"]
