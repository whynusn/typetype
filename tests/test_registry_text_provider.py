from pathlib import Path
from unittest.mock import MagicMock
import json

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
    config: RegistryConfig | None = None,
    responses: list | None = None,
    tmp_path: Path | None = None,
) -> RegistryTextProvider:
    cfg = config or RegistryConfig(primary_url="https://cdn.example.com")
    cache = tmp_path or Path("/tmp/registry_cache_test")
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


def test_get_catalog_returns_items_from_index():
    provider = _make_provider(
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
        ]
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


def test_get_catalog_returns_empty_on_http_error():
    provider = _make_provider(responses=[_mock_response(None, 404)])
    assert provider.get_catalog() == []


def test_get_catalog_returns_empty_on_connect_error():
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = httpx.ConnectError("no route")
    provider = RegistryTextProvider(
        RegistryConfig(primary_url="https://cdn.example.com"),
        Path("/tmp/cache"),
        http_client=client,
    )
    assert provider.get_catalog() == []


def test_get_catalog_falls_back_to_mirror():
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = _mock_response(None, 404)
    mirror = _mock_response(
        {"sources": [{"source_key": "mirror_only", "label": "镜像"}]}
    )
    provider = _make_provider(config, responses=[primary, mirror])
    result = provider.get_catalog()
    assert len(result) == 1
    assert result[0].source_key == "mirror_only"


# ---------------------------------------------------------------------------
# fetch_text_by_key
# ---------------------------------------------------------------------------


def test_fetch_text_by_key_returns_text():
    provider = _make_provider(
        responses=[
            _mock_response(
                {
                    "content": "你好世界",
                    "text_id": 42,
                    "title": "测试文章",
                }
            )
        ]
    )
    result = provider.fetch_text_by_key("test_article")
    assert result == FetchedText(content="你好世界", text_id=42, title="测试文章")


def test_fetch_text_by_key_returns_none_for_missing_key():
    provider = _make_provider(responses=[_mock_response(None, 404)])
    assert provider.fetch_text_by_key("nonexistent") is None


def test_fetch_text_by_key_enforces_max_content_bytes():
    config = RegistryConfig(primary_url="https://cdn.example.com", max_content_bytes=10)
    provider = _make_provider(
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


def test_fetch_text_by_key_falls_back_to_mirror():
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = _mock_response(None, 404)
    mirror = _mock_response({"content": "mirror text", "title": "Mirror"})
    provider = _make_provider(config, responses=[primary, mirror])
    result = provider.fetch_text_by_key("mirror_only")
    assert result is not None
    assert result.content == "mirror text"


# ---------------------------------------------------------------------------
# fetch_text_by_client_id
# ---------------------------------------------------------------------------


def test_fetch_text_by_client_id_returns_none():
    provider = _make_provider()
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
def test_validate_source_key_rejects_traversal(bad_key):
    provider = _make_provider()
    assert provider.fetch_text_by_key(bad_key) is None


# ---------------------------------------------------------------------------
# Content sanitization
# ---------------------------------------------------------------------------


def test_sanitize_content_removes_control_chars():
    provider = _make_provider(
        responses=[
            _mock_response(
                {
                    "content": "hello\x00world\x01test\nkeep\r\n",
                }
            )
        ]
    )
    result = provider.fetch_text_by_key("ctrl")
    assert result is not None
    # \x00 and \x01 stripped, \n and \r preserved
    assert result.content == "helloworldtest\nkeep\r\n"
