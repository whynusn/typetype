"""SmartRouteSelector：候选派生 / 实时选路 / 失败冷却 / TTL 缓存 / 接入点。

覆盖：
- 候选派生（原始 → jsDelivr → 前缀镜像 → 显式镜像，去重；file:// 不路由）
- 探测排序（低延迟优先）、探测失败冷却、TTL 内不重复探测
- record 回写（成功 EWMA / 失败指数退避冷却）
- OttConfig 新字段归一化与序列化往返
- OttCachedFetcher / RepoManifestCache / ScriptCache 的 router 接入分支
  （router=None 的固定 failover 兼容路径由各模块既有测试覆盖）
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from src.backend.config.runtime_config import OttConfig, RuntimeConfig
from src.backend.integration.ott_cached_fetcher import OttCachedFetcher
from src.backend.integration.ott_repo_manifest import RepoManifestCache
from src.backend.integration.ott_script_client import ScriptCache
from src.backend.integration.smart_router import SmartRouteSelector

RAW_URL = "https://raw.githubusercontent.com/owner/repo/main/ott-repo.json"
JSDELIVR_URL = "https://cdn.jsdelivr.net/gh/owner/repo@main/ott-repo.json"


def _make_router(**kwargs) -> SmartRouteSelector:
    return SmartRouteSelector(OttConfig(**kwargs))


@pytest.fixture
def no_probe(monkeypatch):
    """禁用探测（测试环境不碰真实网络）→ 排序退化为派生顺序。"""

    def offline(url: str):
        raise httpx.ConnectError("offline test")

    monkeypatch.setattr(SmartRouteSelector, "_probe_url", offline)


# ----------------------------------------------------------------------
# 候选派生
# ----------------------------------------------------------------------


def test_derive_raw_jsdelivr_only(no_probe):
    router = _make_router()
    cands = router.ordered_candidates(RAW_URL)
    assert cands == [RAW_URL, JSDELIVR_URL]


def test_derive_with_prefix_mirrors_and_explicit_mirrors(no_probe):
    router = _make_router(
        route_mirrors=["https://gh-proxy.com/", "https://m.example.com/"]
    )
    cands = router.ordered_candidates(
        RAW_URL, mirrors=["https://mirror1.example.org/ott-repo.json"]
    )
    # 派生顺序：原始 → jsDelivr → 前缀镜像 → 显式镜像（无统计时按派生顺序）
    assert cands[0] == RAW_URL
    assert cands[1] == JSDELIVR_URL
    assert cands[2] == "https://gh-proxy.com/" + RAW_URL
    assert cands[3] == "https://m.example.com/" + RAW_URL
    assert cands[4] == "https://mirror1.example.org/ott-repo.json"


def test_derive_deduplicates_same_url(no_probe):
    router = _make_router()
    cands = router.ordered_candidates(RAW_URL, mirrors=[RAW_URL, JSDELIVR_URL])
    assert cands == [RAW_URL, JSDELIVR_URL]


def test_derive_file_url_not_routed(no_probe):
    router = _make_router(route_mirrors=["https://gh-proxy.com/"])
    assert router.ordered_candidates("file:///tmp/ott-repo.json") == [
        "file:///tmp/ott-repo.json"
    ]


def test_derive_non_raw_url_has_no_jsdelivr(no_probe):
    router = _make_router()
    assert router.ordered_candidates("https://texts.example.org/ott-repo.json") == [
        "https://texts.example.org/ott-repo.json"
    ]


# ----------------------------------------------------------------------
# 探测排序 / 冷却 / TTL
# ----------------------------------------------------------------------


def test_orders_by_probe_latency(monkeypatch):
    router = _make_router(route_mirrors=["https://m.example.com/"])
    probe_calls: dict[str, int] = {}

    def fake_probe(url: str):
        probe_calls[url] = probe_calls.get(url, 0) + 1
        if "cdn.jsdelivr.net" in url:
            return True, 0.05
        if "m.example.com" in url:
            return True, 0.3
        return True, 1.2  # raw 最慢

    monkeypatch.setattr(router, "_probe_url", fake_probe)
    cands = router.ordered_candidates(RAW_URL)
    assert cands[0] == JSDELIVR_URL  # 延迟最低
    assert cands[1] == "https://m.example.com/" + RAW_URL
    assert cands[2] == RAW_URL  # 延迟最高
    # TTL 内复用：再次调用不再探测
    router.ordered_candidates(RAW_URL)
    assert sum(probe_calls.values()) == 3


def test_failed_probe_sorted_last_and_cooldown(monkeypatch):
    router = _make_router()
    monkeypatch.setattr(
        router, "_probe_url", lambda url: (False, 0.0) if "raw" in url else (True, 0.1)
    )
    cands = router.ordered_candidates(RAW_URL)
    assert cands[0] == JSDELIVR_URL
    assert cands[1] == RAW_URL  # 探测失败 → 冷却 → 排最后

    # 冷却 + TTL 内：不再探测任何候选
    extra_calls: list[str] = []

    def fake_probe2(url: str):
        extra_calls.append(url)
        return True, 0.1

    monkeypatch.setattr(router, "_probe_url", fake_probe2)
    router.ordered_candidates(RAW_URL)
    assert extra_calls == []


def test_cooldown_expiry_allows_reprobe(monkeypatch):
    router = _make_router()
    monkeypatch.setattr(router, "_probe_url", lambda url: (False, 0.0))
    router.ordered_candidates(RAW_URL)  # raw 失败冷却
    # 手动推进：清掉冷却，制造 TTL 过期
    with router._lock:
        stat = router._stats["raw.githubusercontent.com"]
        stat.cooldown_until = 0.0
        stat.last_probe = 0.0
    calls: list[str] = []

    def fake_probe(url: str):
        calls.append(url)
        return True, 0.01

    monkeypatch.setattr(router, "_probe_url", fake_probe)
    router.ordered_candidates(RAW_URL)
    assert "raw.githubusercontent.com" in " ".join(calls)  # 重新探测


def test_record_updates_ewma_and_cooldown():
    router = _make_router()
    router.record("https://a.example.com/x.json", ok=False)
    router.record("https://a.example.com/x.json", ok=False)
    stat = router._stats["a.example.com"]
    assert stat.consecutive_failures == 2
    assert stat.cooldown_until > 0
    router.record("https://a.example.com/x.json", ok=True, latency=0.5)
    assert router._stats["a.example.com"].consecutive_failures == 0
    assert router._stats["a.example.com"].latency_ewma == pytest.approx(0.5)


def test_record_backoff_escalates_then_caps():
    import time as _time

    router = _make_router()
    router.record("https://a.example.com/x", ok=False)
    first = router._stats["a.example.com"].cooldown_until
    for _ in range(5):
        router.record("https://a.example.com/x", ok=False)
    last = router._stats["a.example.com"].cooldown_until
    assert last - first >= 30.0  # 指数退避至少翻倍
    for _ in range(10):
        router.record("https://a.example.com/x", ok=False)
    capped = router._stats["a.example.com"].cooldown_until
    assert capped - _time.monotonic() <= 300.0  # 封顶 300s


def test_probe_network_error_is_tolerated(monkeypatch):
    """探测抛异常（无网/超时）→ 静默退化为派生顺序，不抛给调用方。"""
    router = _make_router()

    def boom(url: str):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(router, "_probe_url", boom)
    cands = router.ordered_candidates(RAW_URL)
    assert cands == [RAW_URL, JSDELIVR_URL]


# ----------------------------------------------------------------------
# OttConfig 字段归一化 + 序列化往返
# ----------------------------------------------------------------------


def test_ott_config_normalizes_route_fields():
    cfg = OttConfig(
        route_mirrors=["https://gh-proxy.com/", "bad", ""],
        route_probe_ttl_seconds=-5,
    )
    assert cfg.route_mirrors == ["https://gh-proxy.com/"]
    assert cfg.route_probe_ttl_seconds == 300


def test_runtime_config_roundtrip_route_fields(tmp_path):
    path = str(tmp_path / "config.json")
    config = RuntimeConfig.load_from_file(path)
    config.ott.route_mirrors = ["https://gh-proxy.com/"]
    config.ott.route_probe_ttl_seconds = 60
    config._save_to_file()
    loaded = RuntimeConfig.load_from_file(path)
    assert loaded.ott.route_mirrors == ["https://gh-proxy.com/"]
    assert loaded.ott.route_probe_ttl_seconds == 60


# ----------------------------------------------------------------------
# 接入点：OttCachedFetcher / RepoManifestCache / ScriptCache（router 分支）
# ----------------------------------------------------------------------


def _mock_http_response(data=None, text="", status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = (
        json.dumps(data).encode("utf-8") if data is not None else text.encode("utf-8")
    )
    response.text = text
    response.headers = {}
    if data is not None:
        response.json.return_value = data
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def test_cached_fetcher_routed_tries_candidates_in_order(tmp_path):
    router = MagicMock()
    router.ordered_candidates.return_value = [
        "https://a.example.com/x.json",
        "https://b.example.com/x.json",
    ]
    payload = {"entry_id": "e1"}
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        _mock_http_response(status_code=500),
        _mock_http_response(data=payload),
    ]
    fetcher = OttCachedFetcher(
        OttConfig(), tmp_path / "cache", client, None, router=router
    )
    result = fetcher.fetch_json_with_cache(
        "k", "https://a.example.com/x.json", force=True
    )
    assert result == payload
    assert router.record.call_count == 2  # 每个候选都回写统计


def test_manifest_cache_routed_uses_router_order(tmp_path):
    router = MagicMock()
    router.ordered_candidates.return_value = [RAW_URL, JSDELIVR_URL]
    manifest = {
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
        "sources": [],
    }
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        _mock_http_response(status_code=500),
        _mock_http_response(data=manifest),
    ]
    cache = RepoManifestCache(tmp_path / "cache", client, None, router=router)
    from src.backend.config.runtime_config import SourceRepoEntry

    repo = SourceRepoEntry(url=RAW_URL)
    assert cache.refresh_manifest(repo) is not None
    urls = [call.args[0] for call in client.get.call_args_list]
    assert urls == [RAW_URL, JSDELIVR_URL]
    assert router.record.call_count == 2


def _mock_stream_context(text: str, status_code: int = 200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    response.iter_text.return_value = iter([text])
    cm = MagicMock()
    cm.__enter__.return_value = response
    return cm


def test_script_cache_routed_tries_candidates_in_order(tmp_path):
    router = MagicMock()
    router.ordered_candidates.return_value = [
        "https://a.example.com/script.py",
        "https://b.example.com/script.py",
    ]
    client = MagicMock(spec=httpx.Client)
    client.stream.side_effect = [
        _mock_stream_context("", status_code=500),
        _mock_stream_context("def fetch_entries(): return []"),
    ]
    cache = ScriptCache(tmp_path / "cache", client, enabled=True, router=router)
    assert cache.get_script("https://a.example.com/script.py") == (
        "def fetch_entries(): return []"
    )
    assert client.stream.call_count == 2
    assert router.record.call_count == 2
