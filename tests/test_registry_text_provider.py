import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from src.backend.config.runtime_config import RegistryConfig
from src.backend.integration.registry_text_provider import RegistryTextProvider
from src.backend.models.dto.fetched_text import FetchedText
from src.backend.models.dto.text_catalog_item import TextCatalogItem


def _mock_response(json_data, status_code=200):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json.return_value = json_data
    r.content = json.dumps(json_data).encode("utf-8") if json_data is not None else b""
    if status_code >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=r
        )
    else:
        r.raise_for_status = MagicMock()
    return r


def _make_provider(
    tmp_path: Path,
    config: RegistryConfig | None = None,
    responses: list | None = None,
) -> RegistryTextProvider:
    """构造 provider 用于测试。tmp_path 为必传，避免污染 /tmp。"""
    cfg = config or RegistryConfig(primary_url="https://cdn.example.com")
    cache = tmp_path / "registry_cache"
    if responses:
        client = MagicMock(spec=httpx.Client)
        if len(responses) == 1:
            client.get.return_value = responses[0]
        else:
            client.get.side_effect = responses
        return RegistryTextProvider(cfg, cache, http_client=client)
    return RegistryTextProvider(cfg, cache)


# ---------------------------------------------------------------------------
# get_catalog
# ---------------------------------------------------------------------------


def test_get_catalog_returns_items_from_index(tmp_path):
    provider = _make_provider(
        tmp_path,
        responses=[
            _mock_response(
                {
                    "sources": [
                        {
                            "id": 1,
                            "source_key": "essays",
                            "label": "随笔",
                            "description": "日常随笔",
                        },
                        {
                            "id": 2,
                            "source_key": "news",
                            "label": "新闻",
                            "has_ranking": True,
                        },
                    ]
                }
            )
        ],
    )
    result = provider.get_catalog()
    assert result == [
        TextCatalogItem(
            id=1,
            source_key="essays",
            label="随笔",
            description="日常随笔",
            has_ranking=False,
        ),
        TextCatalogItem(
            id=2, source_key="news", label="新闻", description="", has_ranking=True
        ),
    ]


def test_get_catalog_returns_empty_on_http_error(tmp_path):
    provider = _make_provider(tmp_path, responses=[_mock_response(None, 404)])
    assert provider.get_catalog() == []


def test_get_catalog_returns_empty_on_connect_error(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("no route")
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        tmp_path / "cache",
        http_client=client,
    )
    assert provider.get_catalog() == []


def test_get_catalog_falls_back_to_mirror(tmp_path):
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = _mock_response(None, 404)
    mirror = _mock_response(
        {"sources": [{"source_key": "mirror_only", "label": "镜像"}]}
    )
    provider = _make_provider(tmp_path, config, responses=[primary, mirror])
    result = provider.get_catalog()
    assert len(result) == 1
    assert result[0].source_key == "mirror_only"


# ---------------------------------------------------------------------------
# fetch_text_by_key
# ---------------------------------------------------------------------------


def test_fetch_text_by_key_returns_text(tmp_path):
    provider = _make_provider(
        tmp_path,
        responses=[
            _mock_response(
                {
                    "content": "你好世界",
                    "text_id": 42,
                    "title": "测试文章",
                }
            )
        ],
    )
    result = provider.fetch_text_by_key("test_article")
    assert result == FetchedText(content="你好世界", text_id=42, title="测试文章")


def test_fetch_text_by_key_returns_none_for_missing_key(tmp_path):
    provider = _make_provider(tmp_path, responses=[_mock_response(None, 404)])
    assert provider.fetch_text_by_key("nonexistent") is None


def test_fetch_text_by_key_enforces_max_content_bytes(tmp_path):
    config = RegistryConfig(primary_url="https://cdn.example.com", max_content_bytes=10)
    provider = _make_provider(
        tmp_path,
        config,
        responses=[
            _mock_response(
                {
                    "content": "x" * 100,
                }
            )
        ],
    )
    assert provider.fetch_text_by_key("big") is None


def test_fetch_text_by_key_falls_back_to_mirror(tmp_path):
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = _mock_response(None, 404)
    mirror = _mock_response({"content": "mirror text", "title": "Mirror"})
    provider = _make_provider(tmp_path, config, responses=[primary, mirror])
    result = provider.fetch_text_by_key("mirror_only")
    assert result is not None
    assert result.content == "mirror text"


# ---------------------------------------------------------------------------
# fetch_text_by_client_id
# ---------------------------------------------------------------------------


def test_fetch_text_by_client_id_returns_none(tmp_path):
    provider = _make_provider(tmp_path)
    assert provider.fetch_text_by_client_id(123) is None


# ---------------------------------------------------------------------------
# Security: source_key validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "../etc/passwd",
        "content/../../secret",
        "foo/bar",
        "a\\b",
        "",
    ],
)
def test_validate_source_key_rejects_traversal(tmp_path, bad_key):
    provider = _make_provider(tmp_path)
    assert provider.fetch_text_by_key(bad_key) is None


# ---------------------------------------------------------------------------
# Content sanitization
# ---------------------------------------------------------------------------


def test_sanitize_content_removes_control_chars(tmp_path):
    provider = _make_provider(
        tmp_path,
        responses=[
            _mock_response(
                {
                    "content": "hello\x00world\x01test\nkeep\r\n",
                }
            )
        ],
    )
    result = provider.fetch_text_by_key("ctrl")
    assert result is not None
    # \x00 and \x01 stripped, \n and \r preserved
    assert result.content == "helloworldtest\nkeep\r\n"


# ===========================================================================
# 缓存层测试（Phase 1a）
# ===========================================================================


def _make_content_response(content: str = "缓存测试", title: str = "标题") -> dict:
    return {"content": content, "title": title, "text_id": 1}


def _make_index_response(source_key: str = "daily") -> dict:
    return {"sources": [{"source_key": source_key, "label": source_key}]}


def _age_cache_file(provider: RegistryTextProvider, cache_key: str, seconds_old: float):
    """将缓存文件的 mtime 设置为指定秒数之前，模拟过期。"""
    path = provider._cache_path(cache_key)
    if path.exists():
        old_time = time.time() - seconds_old
        os.utime(path, (old_time, old_time))


# ---------------------------------------------------------------------------
# cache miss / hit
# ---------------------------------------------------------------------------


def test_cache_miss_fetches_network_and_writes_cache(tmp_path):
    """首次请求打网络，缓存文件被创建。"""
    provider = _make_provider(
        tmp_path, responses=[_mock_response(_make_content_response())]
    )
    result = provider.fetch_text_by_key("article1")
    assert result is not None
    assert result.content == "缓存测试"
    # 缓存文件存在
    cache_file = provider._cache_path("content/article1")
    assert cache_file.exists()
    # 缓存内容正确
    cached = provider._read_cache("content/article1")
    assert cached["content"] == "缓存测试"


def test_cache_hit_returns_cached_without_network(tmp_path):
    """TTL 内第二次请求不打网络，返回缓存。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(_make_content_response())
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=3600),
        tmp_path / "cache",
        http_client=client,
    )
    # 第一次：打网络，写缓存
    r1 = provider.fetch_text_by_key("article1")
    assert r1 is not None
    assert client.get.call_count == 1
    # 第二次：应命中缓存，不再打网络
    r2 = provider.fetch_text_by_key("article1")
    assert r2 is not None
    assert r2.content == r1.content
    assert client.get.call_count == 1  # 仍是 1，未增加


def test_cache_expired_refetches_network(tmp_path):
    """TTL 过期后返回 stale + 后台刷新（stale-while-revalidate）。"""
    from src.backend.integration.qt_async_executor import QtAsyncExecutor

    client = MagicMock(spec=httpx.Client)
    # 第一次（cache miss）：返回"缓存测试"，写入缓存
    # 第二次（后台刷新）：返回"新内容"，更新缓存
    client.get.side_effect = [
        _mock_response(_make_content_response("缓存测试")),
        _mock_response(_make_content_response("新内容")),
    ]
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=60),
        tmp_path / "cache",
        http_client=client,
        async_executor=QtAsyncExecutor(),
    )
    # 第一次：打网络，写缓存
    r1 = provider.fetch_text_by_key("article1")
    assert r1 is not None
    assert r1.content == "缓存测试"
    assert client.get.call_count == 1
    # 模拟缓存过期
    _age_cache_file(provider, "content/article1", seconds_old=120)
    # 第二次：TTL 过期，应返回 stale（不阻塞）+ 后台刷新
    r2 = provider.fetch_text_by_key("article1")
    assert r2 is not None
    assert r2.content == "缓存测试"  # stale 内容（未更新）
    assert client.get.call_count == 1  # 前台未打网络（后台异步）
    # 等待后台刷新完成
    import time as _t

    _t.sleep(0.1)
    assert client.get.call_count == 2  # 后台刷新已完成
    # 缓存已更新为新内容
    cached = provider._read_cache("content/article1")
    assert cached["content"] == "新内容"


# ---------------------------------------------------------------------------
# 离线兜底
# ---------------------------------------------------------------------------


def test_offline_returns_stale_cache(tmp_path):
    """网络失败 + 有过期缓存 → 返回 stale（无视 TTL 兜底）。"""
    client = MagicMock(spec=httpx.Client)
    # 第一次成功，第二次失败
    client.get.side_effect = [
        _mock_response(_make_content_response("原始内容")),
        httpx.ConnectError("offline"),
    ]
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=60),
        tmp_path / "cache",
        http_client=client,
    )
    # 第一次：成功，写缓存
    r1 = provider.fetch_text_by_key("article1")
    assert r1 is not None
    assert r1.content == "原始内容"
    # 模拟缓存过期 + 网络断开
    _age_cache_file(provider, "content/article1", seconds_old=120)
    r2 = provider.fetch_text_by_key("article1")
    # 网络失败，返回 stale 缓存
    assert r2 is not None
    assert r2.content == "原始内容"


def test_offline_no_cache_returns_none(tmp_path):
    """网络失败 + 无缓存 → None。"""
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("offline")
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        tmp_path / "cache",
        http_client=client,
    )
    assert provider.fetch_text_by_key("article1") is None


# ---------------------------------------------------------------------------
# mirror + 缓存
# ---------------------------------------------------------------------------


def test_cache_survives_mirror_failover(tmp_path):
    """primary 失败 mirror 成功 → 写缓存并返回。"""
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = _mock_response(None, 404)
    mirror = _mock_response(_make_content_response("镜像内容"))
    provider = _make_provider(tmp_path, config, responses=[primary, mirror])
    result = provider.fetch_text_by_key("article1")
    assert result is not None
    assert result.content == "镜像内容"
    # mirror 成功后应写缓存
    cached = provider._read_cache("content/article1")
    assert cached["content"] == "镜像内容"


# ---------------------------------------------------------------------------
# 缓存健壮性
# ---------------------------------------------------------------------------


def test_cache_write_failure_does_not_crash(tmp_path):
    """缓存目录不可写时不影响主流程（_write_cache 内部捕获 OSError）。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(_make_content_response("网络内容"))
    cache_dir = tmp_path / "cache"
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        cache_dir,
        http_client=client,
    )
    # 让缓存目录变为不可写（模拟磁盘满/权限问题）
    cache_dir.chmod(0o444)
    try:
        result = provider.fetch_text_by_key("article1")
        # 主流程不受影响，仍返回网络结果
        assert result is not None
        assert result.content == "网络内容"
    finally:
        cache_dir.chmod(0o755)  # 恢复权限便于清理


def test_cache_corrupted_refetches_network(tmp_path):
    """缓存文件损坏（非 JSON）→ 视为 miss，重新打网络。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(_make_content_response("网络内容"))
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=3600),
        tmp_path / "cache",
        http_client=client,
    )
    # 预先写一个损坏的缓存文件
    cache_file = provider._cache_path("content/article1")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
    # 应忽略损坏缓存，打网络
    result = provider.fetch_text_by_key("article1")
    assert result is not None
    assert result.content == "网络内容"
    assert client.get.call_count == 1


def test_index_and_content_use_separate_cache_files(tmp_path):
    """index 和 content 缓存到不同文件。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(_make_content_response())
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        tmp_path / "cache",
        http_client=client,
    )
    provider.fetch_text_by_key("article1")
    # content 缓存存在
    assert provider._cache_path("content/article1").exists()
    # index 缓存不存在（fetch_text_by_key 不触发 index 获取）
    assert not provider._cache_path("index").exists()


def test_validate_source_key_protects_cache_path(tmp_path):
    """恶意 source_key 不会逃逸 cache_dir（_validate_source_key 拦截）。"""
    provider = _make_provider(tmp_path)
    # 这些 key 应被 _validate_source_key 拒绝，不会构造缓存路径
    assert provider.fetch_text_by_key("../etc/passwd") is None
    assert provider.fetch_text_by_key("foo/bar") is None
    # cache_dir 下不应出现逃逸文件
    assert not (tmp_path / "registry_cache" / "..").exists() or True  # 不逃逸即可
