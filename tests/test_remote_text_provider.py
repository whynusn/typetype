from src.backend.integration.remote_text_provider import RemoteTextProvider
from src.backend.models.dto.text_catalog_item import TextCatalogItem


class DummyApiClient:
    def __init__(self, response):
        self._response = response
        self.last_call = None

    def request(self, method, url, headers=None):
        self.last_call = {
            "method": method,
            "url": url,
            "headers": headers,
        }
        return self._response


def test_get_catalog_builds_text_catalog_items_from_response():
    api_client = DummyApiClient(
        {
            "data": [
                {
                    "id": 1,
                    "sourceKey": "cloud_001",
                    "label": "云端文章",
                    "category": "每日推荐",
                }
            ]
        }
    )
    provider = RemoteTextProvider(
        base_url="https://example.com",
        api_client=api_client,
    )

    result = provider.get_catalog()

    assert result == [
        TextCatalogItem(
            id=1,
            source_key="cloud_001",
            label="云端文章",
            description="每日推荐",
            has_ranking=True,
        )
    ]
    assert api_client.last_call == {
        "method": "GET",
        "url": "https://example.com/api/v1/texts/catalog",
        "headers": None,
    }


def test_fetch_text_by_key_accepts_data_content_response():
    api_client = DummyApiClient(
        {"data": {"id": 12, "title": "标题", "content": "正文"}}
    )
    provider = RemoteTextProvider(
        base_url="https://example.com",
        api_client=api_client,
    )

    result = provider.fetch_text_by_key("old")

    assert result is not None
    assert result.text_id == 12
    assert result.title == "标题"
    assert result.content == "正文"
    assert api_client.last_call == {
        "method": "GET",
        "url": "https://example.com/api/v1/texts/latest/old",
        "headers": {},
    }


def test_fetch_text_by_key_accepts_legacy_text_field_response():
    api_client = DummyApiClient(
        {"data": {"textId": 34, "name": "旧文", "text": "正文"}}
    )
    provider = RemoteTextProvider(
        base_url="https://example.com",
        api_client=api_client,
    )

    result = provider.fetch_text_by_key("old")

    assert result is not None
    assert result.text_id == 34
    assert result.title == "旧文"
    assert result.content == "正文"


def test_fetch_text_by_key_accepts_top_level_content_response():
    api_client = DummyApiClient({"id": 56, "content": "正文"})
    provider = RemoteTextProvider(
        base_url="https://example.com",
        api_client=api_client,
    )

    result = provider.fetch_text_by_key("old")

    assert result is not None
    assert result.text_id == 56
    assert result.content == "正文"


def test_fetch_text_by_key_returns_none_when_content_missing():
    api_client = DummyApiClient({"data": {"id": 56, "title": "无正文"}})
    provider = RemoteTextProvider(
        base_url="https://example.com",
        api_client=api_client,
    )

    assert provider.fetch_text_by_key("old") is None
