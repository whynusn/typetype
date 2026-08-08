import httpx
import pytest

from src.backend.config.runtime_config import RegistryConfig
from src.backend.models.dto.fetched_text import FetchedText
from src.backend.models.dto.text_catalog_item import TextCatalogItem

from .ott_text_provider_helpers import (
    make_provider,
    make_provider_with_client,
    mock_response,
)


def test_get_catalog_returns_items_from_index(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
        [
            mock_response(
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

    assert provider.get_catalog() == [
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
    provider = make_provider(tmp_path, responses=[mock_response(None, 404)])
    assert provider.get_catalog() == []


def test_get_catalog_returns_empty_on_connect_error(tmp_path):
    provider, client = make_provider_with_client(tmp_path)
    client.get.side_effect = httpx.ConnectError("no route")
    assert provider.get_catalog() == []


def test_get_catalog_falls_back_to_mirror(tmp_path):
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    primary = mock_response(None, 404)
    mirror = mock_response(
        {"sources": [{"source_key": "mirror_only", "label": "镜像"}]}
    )
    provider = make_provider(tmp_path, config, [primary, mirror])

    result = provider.get_catalog()

    assert len(result) == 1
    assert result[0].source_key == "mirror_only"


def test_fetch_text_by_key_returns_text(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
        [mock_response({"content": "你好世界", "text_id": 42, "title": "测试文章"})],
    )

    result = provider.fetch_text_by_key("test_article")

    assert result == FetchedText(content="你好世界", text_id=42, title="测试文章")


def test_fetch_text_by_key_returns_none_for_missing_key(tmp_path):
    provider = make_provider(tmp_path, responses=[mock_response(None, 404)])
    assert provider.fetch_text_by_key("nonexistent") is None


def test_fetch_text_by_key_enforces_max_content_bytes(tmp_path):
    config = RegistryConfig(primary_url="https://cdn.example.com", max_content_bytes=10)
    provider = make_provider(tmp_path, config, [mock_response({"content": "x" * 100})])
    assert provider.fetch_text_by_key("big") is None


def test_fetch_text_by_key_falls_back_to_mirror(tmp_path):
    config = RegistryConfig(
        primary_url="https://primary.example.com",
        mirror_url="https://mirror.example.com",
    )
    provider = make_provider(
        tmp_path,
        config,
        [
            mock_response(None, 404),
            mock_response({"content": "mirror text", "title": "Mirror"}),
        ],
    )

    result = provider.fetch_text_by_key("mirror_only")

    assert result is not None
    assert result.content == "mirror text"


def test_fetch_text_by_client_id_returns_none(tmp_path):
    provider = make_provider(tmp_path)
    assert provider.fetch_text_by_client_id(123) is None


@pytest.mark.parametrize(
    "bad_key",
    ["../etc/passwd", "content/../../secret", "foo/bar", "a\\b", ""],
)
def test_validate_source_key_rejects_traversal(tmp_path, bad_key):
    provider = make_provider(tmp_path)
    assert provider.fetch_text_by_key(bad_key) is None


def test_sanitize_content_removes_control_chars(tmp_path):
    provider = make_provider(
        tmp_path,
        responses=[mock_response({"content": "hello\x00world\x01test\nkeep\r\n"})],
    )

    result = provider.fetch_text_by_key("ctrl")

    assert result is not None
    assert result.content == "helloworldtest\nkeep\r\n"
