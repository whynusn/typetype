"""OttClient 协议路由与分页边界测试。"""

from __future__ import annotations

from src.backend.integration.ott_client import OttClient


def _make_client(fetch_json, fetch_text=None, authority: str = "auth") -> OttClient:
    return OttClient(
        primary_url="https://example.com",
        mirror_url="",
        authority=authority,
        fetch_json=fetch_json,
        fetch_text=fetch_text or (lambda *args: None),
        max_content_bytes=1_048_576,
    )


def test_pagination_interruption_returns_none() -> None:
    """任一页请求失败 → 返回 None（不得把半截列表当完整结果）。"""
    calls = {"n": 0}

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"entries": [{"entry_id": "e1", "title": "T1"}], "pages": 3}
        return None  # 第二页失败

    client = _make_client(fetch_json)
    assert client.list_entries() is None
    # service 分页中断后（第 2 页）还会尝试 static fallback
    assert calls["n"] >= 2


def test_pagination_multi_page_success() -> None:
    """多页均成功 → 聚合全部条目。"""
    calls = {"n": 0}

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"entries": [{"entry_id": "e1"}], "pages": 2}
        return {"entries": [{"entry_id": "e2"}], "pages": 2}

    client = _make_client(fetch_json)
    entries = client.list_entries()
    assert entries is not None
    assert [e["entry_id"] for e in entries] == ["e1", "e2"]


def test_static_segment_cache_key_contains_entry_id() -> None:
    """静态分段缓存键含 entry_id，防不同 entry 同 revision/index 串缓存。"""
    seen_keys = []

    def fetch_text(cache_key, url, mirror_url, max_bytes):
        seen_keys.append(cache_key)
        return "segment-content"

    client = _make_client(lambda *args: None, fetch_text=fetch_text)
    seg = client.get_segment("entry_a", "rev_1", 2)
    assert seg is not None
    assert seg["content"] == "segment-content"
    assert seen_keys == ["ott/static/segments/entry_a/rev_1/2"]
