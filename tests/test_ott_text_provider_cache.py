import os
import time
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import RegistryConfig
from src.backend.integration.ott_text_provider import OttTextProvider

from .ott_text_provider_helpers import (
    make_content_response,
    make_provider,
    mock_response,
)


def _age_cache_file(provider: OttTextProvider, cache_key: str, seconds_old: float):
    path = provider._cache_path(cache_key)
    if path.exists():
        old_time = time.time() - seconds_old
        os.utime(path, (old_time, old_time))


def test_cache_miss_fetches_network_and_writes_cache(tmp_path):
    provider = make_provider(
        tmp_path, responses=[mock_response(make_content_response())]
    )

    result = provider.fetch_text_by_key("article1")

    assert result is not None
    assert result.content == "缓存测试"
    assert provider._cache_path("content/article1").exists()
    cached = provider._read_cache("content/article1")
    assert cached is not None
    assert cached["content"] == "缓存测试"


def test_cache_hit_returns_cached_without_network(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response(make_content_response())
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=3600),
        tmp_path / "cache",
        http_client=client,
    )

    first = provider.fetch_text_by_key("article1")
    second = provider.fetch_text_by_key("article1")

    assert first is not None
    assert second is not None
    assert second.content == first.content
    assert client.get.call_count == 1


def test_cache_expired_refetches_network(tmp_path):
    from src.backend.integration.qt_async_executor import QtAsyncExecutor

    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        mock_response(make_content_response("缓存测试")),
        mock_response(make_content_response("新内容")),
    ]
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=60),
        tmp_path / "cache",
        http_client=client,
        async_executor=QtAsyncExecutor(),
    )

    first = provider.fetch_text_by_key("article1")
    _age_cache_file(provider, "content/article1", seconds_old=120)
    second = provider.fetch_text_by_key("article1")
    time.sleep(0.1)
    cached = provider._read_cache("content/article1")

    assert first is not None
    assert first.content == "缓存测试"
    assert second is not None
    assert second.content == "缓存测试"
    assert client.get.call_count == 2
    assert cached is not None
    assert cached["content"] == "新内容"


def test_offline_returns_stale_cache(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        mock_response(make_content_response("原始内容")),
        httpx.ConnectError("offline"),
    ]
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=60),
        tmp_path / "cache",
        http_client=client,
    )

    first = provider.fetch_text_by_key("article1")
    _age_cache_file(provider, "content/article1", seconds_old=120)
    second = provider.fetch_text_by_key("article1")

    assert first is not None
    assert first.content == "原始内容"
    assert second is not None
    assert second.content == "原始内容"


def test_offline_no_cache_returns_none(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("offline")
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        tmp_path / "cache",
        http_client=client,
    )
    assert provider.fetch_text_by_key("article1") is None


def test_cache_survives_mirror_failover(tmp_path):
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    provider = make_provider(
        tmp_path,
        config,
        [mock_response(None, 404), mock_response(make_content_response("镜像内容"))],
    )

    result = provider.fetch_text_by_key("article1")
    cached = provider._read_cache("content/article1")

    assert result is not None
    assert result.content == "镜像内容"
    assert cached is not None
    assert cached["content"] == "镜像内容"


def test_cache_write_failure_does_not_crash(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response(make_content_response("网络内容"))
    cache_dir = tmp_path / "cache"
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        cache_dir,
        http_client=client,
    )

    cache_dir.chmod(0o444)
    try:
        result = provider.fetch_text_by_key("article1")
        assert result is not None
        assert result.content == "网络内容"
    finally:
        cache_dir.chmod(0o755)


def test_cache_corrupted_refetches_network(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response(make_content_response("网络内容"))
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com", cache_ttl_seconds=3600),
        tmp_path / "cache",
        http_client=client,
    )
    cache_file = provider._cache_path("content/article1")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

    result = provider.fetch_text_by_key("article1")

    assert result is not None
    assert result.content == "网络内容"
    assert client.get.call_count == 1


def test_index_and_content_use_separate_cache_files(tmp_path):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_response(make_content_response())
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        tmp_path / "cache",
        http_client=client,
    )

    provider.fetch_text_by_key("article1")

    assert provider._cache_path("content/article1").exists()
    assert not provider._cache_path("index").exists()


def test_validate_source_key_protects_cache_path(tmp_path):
    provider = make_provider(tmp_path)
    assert provider.fetch_text_by_key("../etc/passwd") is None
    assert provider.fetch_text_by_key("foo/bar") is None
