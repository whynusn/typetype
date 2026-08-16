"""OttCachedFetcher 缓存决策树测试（网络 / 磁盘缓存 / TTL / 镜像 failover）。

单实例 OttTextProvider 已删除（ADR-013 决策 5），缓存职责收敛到
OttCachedFetcher（federation 路径复用）。本文件直接测 OttCachedFetcher。
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import OttConfig
from src.backend.integration.ott_cached_fetcher import OttCachedFetcher


def mock_response(json_data, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.content = json.dumps(json_data).encode("utf-8") if json_data else b""
    response.text = json.dumps(json_data) if json_data else ""
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def mock_text_response(text: str, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = text.encode("utf-8")
    response.text = text
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def make_fetcher(
    tmp_path: Path,
    config: "OttConfig | None" = None,
    client: MagicMock | None = None,
    async_executor=None,
) -> OttCachedFetcher:
    cache_dir = tmp_path / "registry_cache"
    return OttCachedFetcher(
        config or OttConfig(),
        cache_dir,
        client or MagicMock(spec=httpx.Client),
        async_executor,
    )


def _age_cache_file(cache_dir: Path, cache_key: str, seconds_old: float) -> None:
    path = cache_dir / f"{cache_key}.json"
    if path.exists():
        old_time = time.time() - seconds_old
        os.utime(path, (old_time, old_time))


class _SyncExecutor:
    """同步执行后台刷新任务，便于测试过期重取路径。"""

    def submit(self, fn) -> None:
        fn()


def test_cache_miss_fetches_network_and_writes_cache(tmp_path):
    fetcher = make_fetcher(
        tmp_path,
        client=MagicMock(
            spec=httpx.Client,
            get=MagicMock(return_value=mock_response({"content": "缓存测试"})),
        ),
    )

    result = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )

    assert result is not None
    assert result["content"] == "缓存测试"
    cached = fetcher.read_cache("content/article1")
    assert cached is not None
    assert cached["content"] == "缓存测试"


def test_cache_hit_returns_cached_without_network(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response({"content": "缓存测试"})
    fetcher = make_fetcher(
        tmp_path,
        config=OttConfig(cache_ttl_seconds=3600),
        client=client,
    )

    first = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )
    second = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )

    assert first is not None
    assert second is not None
    assert second == first
    assert client.get.call_count == 1


def test_cache_expired_refetches_network(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        mock_response({"content": "缓存测试"}),
        mock_response({"content": "新内容"}),
    ]
    fetcher = make_fetcher(
        tmp_path,
        config=OttConfig(cache_ttl_seconds=60),
        client=client,
        async_executor=_SyncExecutor(),
    )

    first = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )
    _age_cache_file(tmp_path / "registry_cache", "content/article1", seconds_old=120)
    second = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )
    cached = fetcher.read_cache("content/article1")

    assert first is not None
    assert first["content"] == "缓存测试"
    assert second is not None
    assert second["content"] == "缓存测试"
    assert client.get.call_count == 2
    assert cached is not None
    assert cached["content"] == "新内容"


def test_offline_returns_stale_cache(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        mock_response({"content": "原始内容"}),
        httpx.ConnectError("offline"),
    ]
    fetcher = make_fetcher(
        tmp_path,
        config=OttConfig(cache_ttl_seconds=60),
        client=client,
        async_executor=_SyncExecutor(),
    )

    first = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )
    _age_cache_file(tmp_path / "registry_cache", "content/article1", seconds_old=120)
    second = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )

    assert first is not None
    assert first["content"] == "原始内容"
    assert second is not None
    assert second["content"] == "原始内容"


def test_offline_no_cache_returns_none(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("offline")
    fetcher = make_fetcher(tmp_path, client=client)

    assert (
        fetcher.fetch_json_with_cache(
            "content/article1", "https://cdn.example.com/content/article1.json"
        )
        is None
    )


def test_cache_survives_mirror_failover(tmp_path):
    config = OttConfig(
        cache_ttl_seconds=3600,
    )
    fetcher = make_fetcher(
        tmp_path,
        config,
        client=MagicMock(
            spec=httpx.Client,
            get=MagicMock(
                side_effect=[
                    mock_response(None, 404),
                    mock_response({"content": "镜像内容"}),
                ]
            ),
        ),
    )

    result = fetcher.fetch_json_with_cache(
        "content/article1",
        "https://primary.example.com/content/article1.json",
        mirror_url="https://mirror.example.com/content/article1.json",
    )
    cached = fetcher.read_cache("content/article1")

    assert result is not None
    assert result["content"] == "镜像内容"
    assert cached is not None
    assert cached["content"] == "镜像内容"


def test_cache_write_failure_does_not_crash(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response({"content": "网络内容"})
    cache_dir = tmp_path / "registry_cache"
    fetcher = OttCachedFetcher(
        OttConfig(),
        cache_dir,
        client,
        None,
    )

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.chmod(0o444)
    try:
        result = fetcher.fetch_json_with_cache(
            "content/article1", "https://cdn.example.com/content/article1.json"
        )
        assert result is not None
        assert result["content"] == "网络内容"
    finally:
        cache_dir.chmod(0o755)


def test_cache_corrupted_refetches_network(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response({"content": "网络内容"})
    fetcher = make_fetcher(
        tmp_path,
        config=OttConfig(cache_ttl_seconds=3600),
        client=client,
    )
    cache_file = tmp_path / "registry_cache" / "content" / "article1.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

    result = fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )

    assert result is not None
    assert result["content"] == "网络内容"
    assert client.get.call_count == 1


def test_index_and_content_use_separate_cache_files(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response({"content": "缓存测试"})
    fetcher = make_fetcher(tmp_path, client=client)

    fetcher.fetch_json_with_cache(
        "content/article1", "https://cdn.example.com/content/article1.json"
    )

    assert (tmp_path / "registry_cache" / "content" / "article1.json").exists()
    assert not (tmp_path / "registry_cache" / "index.json").exists()


def test_fetch_text_with_cache_roundtrip(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_text_response("分段正文")
    fetcher = make_fetcher(tmp_path, client=client)

    result = fetcher.fetch_text_with_cache(
        "segments/rev_1/1", "https://cdn.example.com/segments/rev_1/1.txt"
    )

    assert result == "分段正文"
    cached = fetcher.read_cache("segments/rev_1/1")
    assert cached is not None
    assert cached["content"] == "分段正文"


def test_local_json_oversize_skipped_before_parse(tmp_path):
    """_read_local_json 先查文件大小，超限不解析（合法 JSON 也拒绝）。"""
    fetcher = make_fetcher(tmp_path)
    big = tmp_path / "big.json"
    big.write_text('{"content": "' + "x" * 500 + '"}', encoding="utf-8")
    assert fetcher._read_local_json(big.as_uri(), max_bytes=100) is None
    assert fetcher._read_local_json(big.as_uri()) is not None


def test_fetch_json_content_length_guard_skips_parse(tmp_path):
    """_fetch_json 用 content-length 预检，声明超限时不解析。"""
    client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.headers = {"content-length": "5000"}
    resp.content = b'{"content": "x"}'  # 实际很小，但声明超大
    resp.raise_for_status = MagicMock()
    client.get.return_value = resp

    fetcher = make_fetcher(tmp_path, client=client)
    assert fetcher._fetch_json("https://example.com/api", max_bytes=100) is None
    resp.json.assert_not_called()


def test_force_bypasses_fresh_cache(tmp_path):
    """force=True 无视 fresh 缓存，直接网络拉取并写回（手动刷新语义）。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response({"content": "旧缓存"})
    fetcher = make_fetcher(tmp_path, client=client)
    assert (
        fetcher.fetch_json_with_cache("k", "https://example.com/a.json")["content"]
        == "旧缓存"
    )

    client.get.return_value = mock_response({"content": "新内容"})
    result = fetcher.fetch_json_with_cache(
        "k", "https://example.com/a.json", force=True
    )
    assert result["content"] == "新内容"
    # 写回缓存（force 命中后，下次普通读取即新内容）
    cached = fetcher.read_cache("k")
    assert cached["content"] == "新内容"


def test_jsdelivr_fallback_on_raw_github_failure(tmp_path):
    """GitHub raw 超时 → jsDelivr CDN 降级（instance 数据面复用 manifest 兜底）。"""
    client = MagicMock(spec=httpx.Client)

    def _get(url):
        if url.startswith("https://raw.githubusercontent.com/"):
            raise httpx.ReadTimeout("read timed out", request=None)
        return mock_response({"content": "cdn 内容"})

    client.get.side_effect = _get
    fetcher = make_fetcher(tmp_path, client=client)
    result = fetcher.fetch_json_with_cache(
        "k", "https://raw.githubusercontent.com/o/r/main/data.json"
    )
    assert result is not None
    assert result["content"] == "cdn 内容"
    assert client.get.call_count == 2

    # 文本面同样降级
    def _get_text(url):
        if url.startswith("https://raw.githubusercontent.com/"):
            raise httpx.ReadTimeout("read timed out", request=None)
        return mock_text_response("cdn 文本内容")

    client.get.side_effect = _get_text
    text = fetcher.fetch_text_with_cache(
        "tk", "https://raw.githubusercontent.com/o/r/main/text.txt"
    )
    assert text == "cdn 文本内容"
    # JSON + 文本各 2 次（raw 失败 + jsDelivr 成功），合计 4
    assert client.get.call_count == 4
