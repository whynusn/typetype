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
