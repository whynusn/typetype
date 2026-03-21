from typing import TYPE_CHECKING, Any

from ..models.text_source import TextCatalogItem

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class TextCatalogService:
    def __init__(self, base_url: str, api_client: "ApiClient"):
        self._base_url = base_url
        self._api_client = api_client

    def get_catalog(self) -> list[TextCatalogItem]:
        """从后端获取文本目录。"""
        try:
            url = f"{self._base_url}/api/v1/texts/catalog"
            response = self._api_client.get_json(url)
            items: list[dict[str, Any]] = []
            if isinstance(response, list):
                items = [item for item in response if isinstance(item, dict)]
            elif isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, list):
                    items = [item for item in data if isinstance(item, dict)]

            if items:
                return [
                    TextCatalogItem(
                        text_id=item.get("text_id", ""),
                        label=item.get("label", ""),
                        description=item.get("description", ""),
                        has_ranking=item.get("has_ranking", False),
                        ranking_type=item.get("ranking_type", ""),
                    )
                    for item in items
                ]
        except Exception:
            pass
        return []

    def fetch_text_by_id(self, text_id: str) -> str | None:
        """根据 text_id 获取完整文本。"""
        try:
            url = f"{self._base_url}/api/v1/texts/{text_id}"
            response = self._api_client.get_json(url)
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, dict):
                    content = data.get("content")
                    return content if isinstance(content, str) else None
                return response.get("content")
        except Exception:
            pass
        return None
