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
