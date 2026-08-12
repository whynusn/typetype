"""OTT Repo manifest 校验与缓存测试。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.backend.config.runtime_config import RuntimeConfig, SourceRepoEntry
from src.backend.integration.ott_repo_manifest import (
    RepoManifestCache,
    manifest_hash,
    repo_cache_key,
    validate_repo_manifest,
)

# 开放文本仓的 schema 路径（兄弟目录），用于跨仓对齐验证
# __file__ = .../typetype/tests/test_ott_repo_manifest.py
# parents[2] = .../work/  →  open-typing-texts 在 .../work/open-typing-texts
OTT_REPO_ROOT = Path(__file__).resolve().parents[2] / "open-typing-texts"
OTT_REPO_SCHEMA_PATH = OTT_REPO_ROOT / "schemas" / "ott-repo.schema.json"


# ---------------------------------------------------------------------------
# validate_repo_manifest
# ---------------------------------------------------------------------------


def _valid_manifest() -> dict:
    return {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "texts.example.org",
        "name": "示例文库",
        "description": "精选中文文本",
        "maintainer": {"name": "someone", "homepage": "https://example.org"},
        "license": "CC-BY-SA-4.0",
        "updated_at": "2026-08-01T00:00:00+08:00",
        "mirrors": [
            {"url": "https://texts.example.org/ott-repo.json", "priority": 1},
        ],
        "trust": {
            "signature": "minisign:...",
            "pubkey": "ed25519:abc",
            "required": False,
        },
        "requires": {"ott_core": ">=1.0", "client_features": ["segmented_content"]},
        "sources": [
            {
                "type": "ott-instance",
                "authority": "texts.example.org",
                "label": "示例静态文库",
                "endpoints": [
                    {
                        "url": "https://texts.example.org/ott/",
                        "profile": "static",
                        "priority": 1,
                    }
                ],
                "tags": ["chinese"],
                "default_enabled": True,
            }
        ],
    }


def test_validate_valid_manifest():
    v = validate_repo_manifest(_valid_manifest())
    assert v is not None
    assert v["protocol"] == "ott-repo"
    assert v["repo_id"] == "texts.example.org"
    assert len(v["sources"]) == 1
    assert v["sources"][0]["authority"] == "texts.example.org"
    assert v["sources"][0]["endpoints"][0]["profile"] == "static"


def test_validate_rejects_bad_protocol():
    m = _valid_manifest()
    m["protocol"] = "nope"
    assert validate_repo_manifest(m) is None


def test_validate_rejects_missing_required_field():
    m = _valid_manifest()
    m.pop("name")
    assert validate_repo_manifest(m) is None


def test_validate_rejects_bad_type():
    m = _valid_manifest()
    m["type"] = "weird"
    assert validate_repo_manifest(m) is None


def test_validate_rejects_empty_mirrors():
    m = _valid_manifest()
    m["mirrors"] = []
    assert validate_repo_manifest(m) is None


def test_validate_rejects_non_dict():
    assert validate_repo_manifest(None) is None
    assert validate_repo_manifest("string") is None
    assert validate_repo_manifest([]) is None


def test_validate_directory_type_with_repository_refs():
    m = {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "directory",
        "repo_id": "dir.example.org",
        "name": "社区目录",
        "mirrors": [{"url": "https://dir.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {"type": "repository-ref", "url": "https://a.org/r.json", "label": "A"},
        ],
    }
    v = validate_repo_manifest(m)
    assert v is not None
    assert v["type"] == "directory"
    assert v["sources"][0]["type"] == "repository-ref"


def test_validate_ott_rule_source():
    m = _valid_manifest()
    m["sources"] = [
        {
            "type": "ott-rule",
            "rule_id": "hitokoto",
            "label": "一言",
            "rule": {
                "kind": "json-api",
                "request": {"url": "https://v1.hitokoto.cn/", "method": "GET"},
                "extract": {"content": "$.hitokoto"},
            },
        }
    ]
    v = validate_repo_manifest(m)
    assert v is not None
    assert v["sources"][0]["rule_id"] == "hitokoto"


def test_validate_ott_bridge_source():
    m = _valid_manifest()
    m["sources"] = [
        {
            "type": "ott-bridge",
            "bridge_kind": "wenlai",
            "endpoint": "https://qingfawen.fcxxz.com",
            "requires_credentials": True,
        }
    ]
    v = validate_repo_manifest(m)
    assert v is not None
    assert v["sources"][0]["bridge_kind"] == "wenlai"


def test_validate_preserves_script_permissions_and_rights():
    m = _valid_manifest()
    m["sources"] = [
        {
            "type": "ott-script",
            "url": "https://example.com/scripts/fetch.py",
            "label": "S",
            "permissions": {
                "network": ["api.example.com"],
                "secrets": ["api_key", "token"],
            },
            "rights": {"min_api_level": 2},
        }
    ]
    v = validate_repo_manifest(m)
    assert v is not None
    src = v["sources"][0]
    assert src["permissions"]["network"] == ["api.example.com"]
    assert src["permissions"]["secrets"] == ["api_key", "token"]
    assert src["rights"]["min_api_level"] == 2


def test_validate_strips_invalid_script_permissions_and_rights():
    m = _valid_manifest()
    m["sources"] = [
        {
            "type": "ott-script",
            "url": "https://example.com/scripts/fetch.py",
            "permissions": {
                "network": ["", 123, "good.com"],
                "secrets": ["  ", "k"],
                "bogus": True,
            },
            "rights": {"min_api_level": "x", "bogus": 1},
        }
    ]
    v = validate_repo_manifest(m)
    src = v["sources"][0]
    assert src["permissions"]["network"] == ["good.com"]
    assert src["permissions"]["secrets"] == ["k"]
    assert "bogus" not in src["permissions"]
    assert src["rights"] == {}


def test_validate_skips_invalid_source_entries():
    m = _valid_manifest()
    m["sources"] = [
        {
            "type": "ott-instance",
            "authority": "good",
            "endpoints": [
                {"url": "https://good.org/", "profile": "static", "priority": 1}
            ],
        },
        {"type": "ott-instance", "authority": ""},  # 无效：缺 authority
        {"type": "unknown"},  # 无效 type
    ]
    v = validate_repo_manifest(m)
    assert v is not None
    assert len(v["sources"]) == 1


def test_validate_endpoints_sorted_by_priority():
    m = _valid_manifest()
    m["sources"][0]["endpoints"] = [
        {"url": "https://b.org/", "profile": "static", "priority": 2},
        {"url": "https://a.org/", "profile": "static", "priority": 1},
    ]
    v = validate_repo_manifest(m)
    assert v is not None
    assert v["sources"][0]["endpoints"][0]["url"] == "https://a.org"


@pytest.mark.skipif(
    not OTT_REPO_SCHEMA_PATH.exists(),
    reason="open-typing-texts 仓未克隆到兄弟目录，跳过跨仓 schema 对齐",
)
def test_validate_output_conforms_to_official_schema():
    """validate_repo_manifest 的归一化输出必须符合 open-typing-texts 的正式 schema。"""
    import jsonschema

    schema = json.loads(OTT_REPO_SCHEMA_PATH.read_text(encoding="utf-8"))
    v = validate_repo_manifest(_valid_manifest())
    assert v is not None
    jsonschema.validate(v, schema)


@pytest.mark.skipif(
    not OTT_REPO_SCHEMA_PATH.exists(),
    reason="open-typing-texts 仓未克隆到兄弟目录，跳过跨仓 schema 对齐",
)
def test_validate_directory_output_conforms_to_schema():
    """directory 类型归一化输出也必须符合 schema。"""
    import jsonschema

    schema = json.loads(OTT_REPO_SCHEMA_PATH.read_text(encoding="utf-8"))
    m = {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "directory",
        "repo_id": "dir.example.org",
        "name": "社区目录",
        "mirrors": [{"url": "https://dir.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {"type": "repository-ref", "url": "https://a.org/r.json", "label": "A"},
        ],
    }
    v = validate_repo_manifest(m)
    assert v is not None
    jsonschema.validate(v, schema)


@pytest.mark.skipif(
    not OTT_REPO_SCHEMA_PATH.exists(),
    reason="open-typing-texts 仓未克隆到兄弟目录，跳过跨仓 schema 对齐",
)
def test_validate_ott_script_output_conforms_to_v11_schema():
    """typetype 归一化器产出的 ott-script 源必须通过 open-typing-texts v1.1 schema。

    跨仓契约：typetype 客户端实现的 manifest 归一化输出，必须能被上游
    repo-manifest-spec v1.1 的正式 schema 接受（L3 签名门槛分发）。
    """
    import jsonschema

    schema = json.loads(OTT_REPO_SCHEMA_PATH.read_text(encoding="utf-8"))
    m = {
        "protocol": "ott-repo",
        "version": "1.1",
        "type": "repository",
        "repo_id": "script.example.org",
        "name": "脚本源仓库",
        "mirrors": [{"url": "https://script.example.org/ott-repo.json", "priority": 1}],
        "sources": [
            {
                "type": "ott-script",
                "url": "https://script.example.org/fetch.py",
                "label": "示例脚本",
                "checksum": "sha256:" + "ab" * 32,
                "permissions": {"network": ["api.example.org"], "secrets": []},
                "rights": {"min_api_level": 2},
                "tags": ["chinese"],
            }
        ],
    }
    v = validate_repo_manifest(m)
    assert v is not None
    assert v["sources"][0]["type"] == "ott-script"
    jsonschema.validate(v, schema)


def test_repo_cache_key_deterministic():
    assert repo_cache_key("https://example.org/r.json") == repo_cache_key(
        "https://example.org/r.json"
    )
    assert repo_cache_key("https://a.org/r.json") != repo_cache_key(
        "https://b.org/r.json"
    )


def test_etag_conditional_request_and_304(tmp_path):
    manifest = _valid_manifest()
    client = MagicMock(spec=httpx.Client)
    ok_resp = _mock_response(json_data=manifest, status_code=200)
    ok_resp.headers = {"etag": '"abc123"'}
    not_modified = _mock_response(json_data=None, status_code=304)
    client.get.side_effect = [ok_resp, not_modified]
    cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=client,
        async_executor=None,
    )
    repo = SourceRepoEntry(
        url="https://texts.example.org/ott-repo.json",
        refresh_ttl_seconds=3600,
    )

    first = cache.refresh_manifest(repo)
    assert first is not None
    first_headers = client.get.call_args_list[0].kwargs.get("headers") or {}
    assert first_headers == {}

    repo.etag = '"abc123"'
    second = cache.refresh_manifest(repo)
    assert second is not None
    second_headers = client.get.call_args_list[1].kwargs.get("headers") or {}
    assert second_headers.get("If-None-Match") == '"abc123"'


def test_mirror_failover_after_primary_failure(tmp_path):
    manifest = _valid_manifest()
    manifest["mirrors"] = [
        {"url": "file:///tmp/ott-repo.json", "priority": 2},
        {"url": "https://mirror.example.org/ott-repo.json", "priority": 1},
    ]
    client = MagicMock(spec=httpx.Client)
    ok_resp = _mock_response(json_data=manifest, status_code=200)
    fail_resp = _mock_response(json_data=None, status_code=500)
    client.get.side_effect = [ok_resp, fail_resp, ok_resp]
    cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=client,
        async_executor=None,
    )
    repo = SourceRepoEntry(url="https://texts.example.org/ott-repo.json")

    assert cache.refresh_manifest(repo) is not None
    assert cache.refresh_manifest(repo) is not None
    urls = [call.args[0] for call in client.get.call_args_list]
    assert urls == [
        "https://texts.example.org/ott-repo.json",
        "https://texts.example.org/ott-repo.json",
        "https://mirror.example.org/ott-repo.json",
    ]


def test_mirror_failover_without_cache_returns_none(tmp_path):
    client = MagicMock(spec=httpx.Client)
    fail_resp = _mock_response(json_data=None, status_code=500)
    client.get.return_value = fail_resp
    cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=client,
        async_executor=None,
    )
    repo = SourceRepoEntry(url="https://texts.example.org/ott-repo.json")

    assert cache.refresh_manifest(repo) is None
    assert client.get.call_count == 1


# ---------------------------------------------------------------------------
# RepoManifestCache (offline / cache-only)
# ---------------------------------------------------------------------------


def _mock_response(json_data=None, text="", status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = (
        json.dumps(json_data).encode("utf-8")
        if json_data is not None
        else text.encode("utf-8")
    )
    response.text = text
    response.headers = {}
    if json_data is not None:
        response.json.return_value = json_data
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def test_cache_returns_none_when_offline_and_no_cache(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("offline")
    cache = RepoManifestCache(tmp_path / "repos", client, None)
    repo = SourceRepoEntry(url="https://offline.org/r.json")
    assert cache.get_manifest(repo) is None


def test_cache_fetches_and_writes_on_miss(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(_valid_manifest())
    cache = RepoManifestCache(tmp_path / "repos", client, None)
    repo = SourceRepoEntry(url="https://fetch.org/r.json")
    result = cache.get_manifest(repo)
    assert result is not None
    assert result["repo_id"] == "texts.example.org"
    # 磁盘已写入
    assert cache.cache_path(repo_cache_key(repo.url)).exists()


def test_cache_uses_cache_when_fresh(tmp_path):
    # 预写缓存
    key = repo_cache_key("https://cached.org/r.json")
    cache_dir = tmp_path / "repos"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    manifest = _valid_manifest()
    manifest["repo_id"] = "cached-org"
    cache_file.write_text(json.dumps(manifest), encoding="utf-8")

    client = MagicMock(spec=httpx.Client)
    cache = RepoManifestCache(cache_dir, client, None)
    repo = SourceRepoEntry(url="https://cached.org/r.json", refresh_ttl_seconds=3600)
    result = cache.get_manifest(repo)
    assert result is not None
    assert result["repo_id"] == "cached-org"
    # 未发起网络请求
    client.get.assert_not_called()


def test_cache_validates_before_caching(tmp_path):
    """无效 manifest 不写入缓存，返回 None。"""
    client = MagicMock(spec=httpx.Client)
    bad = {"protocol": "nope"}
    client.get.return_value = _mock_response(bad)
    cache = RepoManifestCache(tmp_path / "repos", client, None)
    repo = SourceRepoEntry(url="https://bad.org/r.json")
    assert cache.get_manifest(repo) is None


def test_cache_clear_specific_and_all(tmp_path):
    manifest = _valid_manifest()
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None)

    url_a = "https://a.org/r.json"
    url_b = "https://b.org/r.json"
    cache.get_manifest(SourceRepoEntry(url=url_a))
    cache.get_manifest(SourceRepoEntry(url=url_b))
    assert cache.cache_path(repo_cache_key(url_a)).exists()
    assert cache.cache_path(repo_cache_key(url_b)).exists()

    cache.clear_cache(url_a)
    assert not cache.cache_path(repo_cache_key(url_a)).exists()
    assert cache.cache_path(repo_cache_key(url_b)).exists()

    cache.clear_cache()
    assert not cache.cache_path(repo_cache_key(url_b)).exists()


# ---------------------------------------------------------------------------
# TOFU 信任状态机（ADR-011 决策 12：首次信任必须 UI 显式确认）
# ---------------------------------------------------------------------------


def _sign_manifest(manifest: dict, priv: Ed25519PrivateKey) -> dict:
    """对 manifest 做 ed25519 签名并写入 trust 字段（与 _verify_trust 同构）。"""
    canonical = {k: v for k, v in manifest.items() if k != "trust"}
    canonical_bytes = json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    sig = priv.sign(canonical_bytes)
    pubkey_hex = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    manifest["trust"] = {
        "signature": f"ed25519:{sig.hex()}",
        "pubkey": f"ed25519:{pubkey_hex}",
        "required": False,
    }
    return manifest


def _config_with_repo(
    tmp_path, *, url: str = "https://repo.example.com/r.json", **entry_kwargs
) -> tuple[RuntimeConfig, SourceRepoEntry]:
    cfg = {"source_repos": [{"url": url, **entry_kwargs}]}
    config = RuntimeConfig._from_dict(cfg)
    config._config_path = str(tmp_path / "config.json")
    return config, config.source_repos.repos[0]


def _verify_with(
    config: RuntimeConfig, tmp_path, manifest: dict, repo: SourceRepoEntry
) -> None:
    cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=MagicMock(spec=httpx.Client),
        async_executor=None,
        runtime_config=config,
    )
    cache._verify_trust(manifest, repo)


def test_first_valid_signature_sets_pending_not_verified(tmp_path):
    """首次有效签名 → pending（固定公钥），不得自动 verified。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    config, repo = _config_with_repo(tmp_path)

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]


def test_confirm_then_refresh_keeps_verified(tmp_path):
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    config, repo = _config_with_repo(
        tmp_path, trust_state="pending", pinned_pubkey=manifest["trust"]["pubkey"]
    )

    config.confirm_source_repo_trust(repo.url)
    assert repo.trust_state == "verified"

    # 用户确认后刷新，同公钥保持 verified
    _verify_with(config, tmp_path, manifest, repo)
    assert repo.trust_state == "verified"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]


def test_reject_sets_unverified_clears_pin_then_reevaluates(tmp_path):
    """拒绝 → unverified + 清空固定公钥；下次刷新重新评估再次进入 pending。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    config, repo = _config_with_repo(
        tmp_path, trust_state="pending", pinned_pubkey=manifest["trust"]["pubkey"]
    )

    config.reject_source_repo_trust(repo.url)
    assert repo.trust_state == "unverified"
    assert repo.pinned_pubkey == ""

    # 订阅未被删除
    assert len(config.source_repos.repos) == 1

    _verify_with(config, tmp_path, manifest, repo)
    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]


def test_key_change_on_verified_sets_pending(tmp_path):
    """已验证仓库公钥变更 → pending（固定新公钥），需用户重新确认/拒绝。"""
    priv_old = Ed25519PrivateKey.generate()
    priv_new = Ed25519PrivateKey.generate()
    manifest_old = _sign_manifest(_valid_manifest(), priv_old)
    manifest_new = _sign_manifest(_valid_manifest(), priv_new)
    config, repo = _config_with_repo(
        tmp_path,
        trust_state="verified",
        pinned_pubkey=manifest_old["trust"]["pubkey"],
    )

    _verify_with(config, tmp_path, manifest_new, repo)

    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest_new["trust"]["pubkey"]

    # 用户拒绝新公钥 → unverified + 清空
    config.reject_source_repo_trust(repo.url)
    assert repo.trust_state == "unverified"
    assert repo.pinned_pubkey == ""


def test_refresh_while_pending_stays_pending(tmp_path):
    """pending 粘性：同公钥刷新不得把 pending 翻转回 verified。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    config, repo = _config_with_repo(
        tmp_path, trust_state="pending", pinned_pubkey=manifest["trust"]["pubkey"]
    )

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]


def test_invalid_signature_sets_failed(tmp_path):
    """签名校验失败（内容被篡改）→ failed，不进入 pending。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    manifest["description"] = "tampered"
    config, repo = _config_with_repo(tmp_path)

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "failed"


def test_missing_signature_sets_unverified(tmp_path):
    """无签名信息 → unverified（不固定公钥、不进入 pending）。"""
    config, repo = _config_with_repo(tmp_path)
    manifest = _valid_manifest()
    manifest.pop("trust", None)

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "unverified"
    assert repo.pinned_pubkey == ""


# ---------------------------------------------------------------------------
# ADR-011 Phase 2.7：revocations[]（内容屏蔽 + key 级撤销）
# ---------------------------------------------------------------------------


def test_revocations_merge_into_blocked_hashes(tmp_path):
    """已确认信任（verified）仓库的 manifest revocations → 并入本地屏蔽清单。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _valid_manifest()
    manifest["revocations"] = [
        {"content_hash": "sha256:deadbeef"},
        {"content_hash": "sha256:beefdead"},
        {"junk": True},  # 非法条目丢弃
    ]
    manifest = _sign_manifest(manifest, priv)
    config, repo = _config_with_repo(
        tmp_path,
        url="https://revoke.org/r.json",
        trust_state="verified",
        pinned_pubkey=manifest["trust"]["pubkey"],
    )
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    assert cache.get_manifest(repo) is not None
    assert "sha256:deadbeef" in config.blocked_content_hashes
    assert "sha256:beefdead" in config.blocked_content_hashes


def test_unsigned_manifest_revocations_not_applied(tmp_path):
    """无签名（unverified）manifest 的 revocations 不并入屏蔽清单（防投毒）。"""
    config, repo = _config_with_repo(tmp_path, url="https://unsigned.org/r.json")
    manifest = _valid_manifest()
    manifest.pop("trust", None)
    manifest["revocations"] = [{"content_hash": "sha256:deadbeef"}]
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    assert cache.get_manifest(repo) is not None
    assert "sha256:deadbeef" not in config.blocked_content_hashes
    assert repo.trust_state == "unverified"


def test_signed_manifest_pending_then_verified_accept(tmp_path):
    """生产路径端到端：raw 签名 manifest 首次 → pending 拒绝替换；确认后接受。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _sign_manifest(_valid_manifest(), priv)
    config, repo = _config_with_repo(tmp_path)
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    # 首次有效签名：pending + 固定公钥，拒绝替换（无旧缓存 → None，未落盘）
    assert cache.refresh_manifest(repo) is None
    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]
    assert not cache.cache_path(repo_cache_key(repo.url)).exists()

    # 用户确认 → verified → 下次刷新接受
    config.confirm_source_repo_trust(repo.url)
    result = cache.refresh_manifest(repo)
    assert result is not None
    assert result["repo_id"] == manifest["repo_id"]
    assert repo.trust_state == "verified"
    assert repo.last_snapshot_hash == manifest_hash(manifest)


def test_signature_verified_on_raw_not_normalized(tmp_path):
    """回归：验签 canonical 以原始字节为准（归一化重构不得影响验签结果）。"""
    priv = Ed25519PrivateKey.generate()
    manifest = _valid_manifest()
    manifest["name"] = "  示例文库  "  # validate 会 strip，改变 canonical 字节
    signed = _sign_manifest(manifest, priv)

    config, repo = _config_with_repo(
        tmp_path,
        trust_state="verified",
        pinned_pubkey=signed["trust"]["pubkey"],
    )
    cache = RepoManifestCache(
        cache_dir=tmp_path / "cache",
        http_client=MagicMock(spec=httpx.Client),
        async_executor=None,
        runtime_config=config,
    )
    # 原始 dict 验签通过
    assert cache._verify_trust(signed, repo) == "verified"
    assert repo.trust_state == "verified"

    # 对照：归一化重构后的 dict 验签必须失败（证明签名口径是原始字节）
    normalized = validate_repo_manifest(signed)
    assert normalized is not None
    config2, repo2 = _config_with_repo(
        tmp_path,
        url="https://normalized.org/r.json",
        trust_state="verified",
        pinned_pubkey=signed["trust"]["pubkey"],
    )
    cache2 = RepoManifestCache(
        cache_dir=tmp_path / "cache2",
        http_client=MagicMock(spec=httpx.Client),
        async_executor=None,
        runtime_config=config2,
    )
    assert cache2._verify_trust(normalized, repo2) == "failed"
    assert repo2.trust_state == "failed"


def test_no_revocations_no_blocked_hashes(tmp_path):
    """无 revocations 的 manifest 不产生任何屏蔽。"""
    config, repo = _config_with_repo(tmp_path, url="https://none.org/r.json")
    manifest = _valid_manifest()
    manifest.pop("trust", None)  # 无签名仓库
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    assert cache.get_manifest(repo) is not None
    assert config.blocked_content_hashes == []


def test_key_revocation_sets_pending(tmp_path):
    """manifest 声明撤销自身公钥 → 信任降级 pending（用户重新确认）。"""
    priv = Ed25519PrivateKey.generate()
    pubkey_hex = (
        "ed25519:"
        + priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    )
    manifest = _valid_manifest()
    manifest["revocations"] = [{"pubkey": pubkey_hex}]
    manifest = _sign_manifest(manifest, priv)  # 撤销声明必须在签名内容内
    config, repo = _config_with_repo(
        tmp_path,
        trust_state="verified",
        pinned_pubkey=manifest["trust"]["pubkey"],
    )

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "pending"
    assert repo.pinned_pubkey == manifest["trust"]["pubkey"]


def test_revocation_of_other_key_does_not_degrade(tmp_path):
    """撤销其他公钥不影响本仓库信任（单公钥模型，只认自身 key 撤销）。"""
    priv = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    other_pubkey = (
        "ed25519:"
        + other.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    )
    manifest = _valid_manifest()
    manifest["revocations"] = [{"pubkey": other_pubkey}]
    manifest = _sign_manifest(manifest, priv)
    config, repo = _config_with_repo(
        tmp_path,
        trust_state="verified",
        pinned_pubkey=manifest["trust"]["pubkey"],
    )

    _verify_with(config, tmp_path, manifest, repo)

    assert repo.trust_state == "verified"


# ---------------------------------------------------------------------------
# ADR-011 Phase 3.6：TUF-lite（expires_at 过期 + snapshot_hash 防回滚）
# ---------------------------------------------------------------------------


def test_cached_expired_manifest_serves_stale(tmp_path):
    """缓存 manifest 自身 expires_at 已过 → 视为 stale：仍返回缓存，不硬失败。"""
    key = repo_cache_key("https://expired.org/r.json")
    cache_dir = tmp_path / "repos"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = _valid_manifest()
    manifest["repo_id"] = "expired-org"
    manifest["expires_at"] = "2020-01-01T00:00:00+00:00"
    (cache_dir / f"{key}.json").write_text(json.dumps(manifest), encoding="utf-8")

    client = MagicMock(spec=httpx.Client)
    cache = RepoManifestCache(cache_dir, client, None)
    repo = SourceRepoEntry(url="https://expired.org/r.json", refresh_ttl_seconds=3600)

    result = cache.get_manifest(repo)
    assert result is not None
    assert result["repo_id"] == "expired-org"
    # async_executor=None → 后台刷新不发起；stale-while-revalidate 只返回缓存
    client.get.assert_not_called()


def test_incoming_expired_manifest_keeps_old_cache(tmp_path):
    """拉取到的 manifest 已过期 → 拒绝（不留 fresh），回退旧缓存。"""
    config, repo = _config_with_repo(tmp_path, url="https://exp.org/r.json")
    client = MagicMock(spec=httpx.Client)
    m1 = _valid_manifest()
    m1.pop("trust", None)  # 无签名仓库
    m2 = _valid_manifest()
    m2.pop("trust", None)
    m2["repo_id"] = "new-content"
    m2["expires_at"] = "2020-01-01T00:00:00+00:00"
    client.get.side_effect = [_mock_response(m1), _mock_response(m2)]
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    first = cache.refresh_manifest(repo)
    assert first is not None
    assert first["repo_id"] == "texts.example.org"

    second = cache.refresh_manifest(repo)
    assert second is not None
    assert second["repo_id"] == "texts.example.org"  # 仍是旧内容


def test_snapshot_hash_rollback_rejected(tmp_path):
    """snapshot_hash 与已接受 manifest 的 hash 不匹配 → 回滚拒绝，缓存不替换。"""
    config, repo = _config_with_repo(tmp_path, url="https://snap.org/r.json")
    client = MagicMock(spec=httpx.Client)
    m1 = _valid_manifest()
    m1.pop("trust", None)  # 无签名仓库
    m2 = _valid_manifest()
    m2.pop("trust", None)
    m2["repo_id"] = "rolled-back"
    m2["snapshot_hash"] = "sha256:" + "0" * 64  # 不可能匹配 m1 的 hash
    client.get.side_effect = [_mock_response(m1), _mock_response(m2)]
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    first = cache.refresh_manifest(repo)
    assert first is not None
    assert repo.last_snapshot_hash == manifest_hash(m1)
    cache_file = cache.cache_path(repo_cache_key(repo.url))
    cached_before = cache_file.read_text(encoding="utf-8")

    second = cache.refresh_manifest(repo)
    assert second is not None
    assert second["repo_id"] == "texts.example.org"  # 回退旧缓存
    assert cache_file.read_text(encoding="utf-8") == cached_before  # 未替换
    assert repo.last_snapshot_hash == manifest_hash(m1)


def test_snapshot_hash_chain_accepted(tmp_path):
    """snapshot_hash 匹配当前已接受 manifest → 链成立，接受新内容。"""
    config, repo = _config_with_repo(tmp_path, url="https://chain.org/r.json")
    client = MagicMock(spec=httpx.Client)
    m1 = _valid_manifest()
    m1.pop("trust", None)  # 无签名仓库
    m2 = _valid_manifest()
    m2.pop("trust", None)
    m2["repo_id"] = "chained-v2"
    m2["snapshot_hash"] = manifest_hash(m1)  # 生产方口径：原始 manifest hash
    client.get.side_effect = [_mock_response(m1), _mock_response(m2)]
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    assert cache.refresh_manifest(repo) is not None
    second = cache.refresh_manifest(repo)
    assert second is not None
    assert second["repo_id"] == "chained-v2"
    assert repo.last_snapshot_hash == manifest_hash(m2)


def test_missing_tuf_fields_no_crash(tmp_path):
    """缺失 revocations/expires_at/snapshot_hash → 旧行为，不崩溃。"""
    config, repo = _config_with_repo(tmp_path, url="https://plain.org/r.json")
    manifest = _valid_manifest()
    manifest.pop("trust", None)  # 无签名仓库
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    result = cache.get_manifest(repo)
    assert result is not None
    assert result["repo_id"] == "texts.example.org"
    assert config.blocked_content_hashes == []
    # 参照恒记录当前服务内容（可选语义：无 snapshot_hash 也推进链参照）
    assert repo.last_snapshot_hash == manifest_hash(manifest)


def test_first_fetch_with_snapshot_hash_establishes_chain(tmp_path):
    """首次拉取（无参照）时 snapshot_hash 不校验，接受并建立链。"""
    config, repo = _config_with_repo(tmp_path, url="https://first.org/r.json")
    manifest = _valid_manifest()
    manifest.pop("trust", None)  # 无签名仓库
    manifest["snapshot_hash"] = "sha256:" + "f" * 64  # 无参照，任意值可接受
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(manifest)
    cache = RepoManifestCache(tmp_path / "repos", client, None, runtime_config=config)

    result = cache.get_manifest(repo)
    assert result is not None
    assert repo.last_snapshot_hash == manifest_hash(manifest)
