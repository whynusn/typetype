"""OttClient 协议路由与分页边界测试。"""

from __future__ import annotations

from src.backend.integration.ott_client import OttClient


def _make_client(
    fetch_json,
    fetch_text=None,
    authority: str = "auth",
    endpoint_profile: str | None = None,
) -> OttClient:
    return OttClient(
        primary_url="https://example.com",
        mirror_url="",
        authority=authority,
        fetch_json=fetch_json,
        fetch_text=fetch_text or (lambda *args: None),
        max_content_bytes=1_048_576,
        endpoint_profile=endpoint_profile,
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


def test_static_profile_skips_service_probe() -> None:
    """endpoint_profile='static' 时只走 Static Profile，不得探测 service 路径。

    回归：内置 file:// 静态源此前被无谓地先打 /ott/v1/entries 分页，
    产生「分页中断: <invalid-url>」噪音警告（ADR-009 边界语义）。
    """
    urls = []

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        urls.append(url)
        return None

    client = _make_client(fetch_json, endpoint_profile="static")
    assert client.list_entries() is None
    assert urls == ["https://example.com/entries.json"]
    assert not any("/ott/v1/entries" in u for u in urls)


def test_service_profile_skips_static_fallback() -> None:
    """endpoint_profile='service' 时只走 Service Profile，不做 static fallback。"""
    urls = []

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        urls.append(url)
        return None

    client = _make_client(fetch_json, endpoint_profile="service")
    assert client.list_entries() is None
    assert all("/ott/v1/entries" in u for u in urls)
    assert not any("entries.json" in u for u in urls)


def test_static_profile_entry_detail_and_segment() -> None:
    """profile 门控同样作用于 get_entry / get_segment（detail 与分段只走 static）。"""
    urls = []

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        urls.append(url)
        if "entries/ent1.json" in url:
            return {"entry_id": "ent1", "content": "hello"}
        return None

    client = _make_client(fetch_json, endpoint_profile="static")
    detail = client.get_entry("ent1")
    assert detail is not None and detail["content"] == "hello"
    assert urls == ["https://example.com/entries/ent1.json"]
    # 分段：static 文本请求，不走 service 分段端点
    fetch_text_urls = []

    def fetch_text(cache_key, url, mirror_url, max_bytes):
        fetch_text_urls.append(url)
        return "abc"

    client2 = _make_client(
        lambda *args: None, fetch_text=fetch_text, endpoint_profile="static"
    )
    seg = client2.get_segment("ent1", "rev1", 1)
    assert seg is not None and seg["content"] == "abc"
    assert fetch_text_urls == ["https://example.com/segments/rev1/1.txt"]
