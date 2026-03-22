from typing import TYPE_CHECKING, Any

from ..infrastructure.network_errors import CatalogServiceError
from ..models.text_source import TextCatalogItem

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class RemoteCatalogTextFetcher:
    """远程文本目录获取器，通过 API 获取目录列表与文本内容。"""

    def __init__(self, base_url: str, api_client: "ApiClient"):
        self._base_url = base_url
        self._api_client = api_client

    def get_catalog(self) -> list[TextCatalogItem]:
        try:
            url = f"{self._base_url}/api/v1/texts/catalog"
            response = self._api_client.request("GET", url)
            if response is None:
                raise CatalogServiceError("文本库目录请求失败")
            items: list[dict[str, Any]] = []
            if isinstance(response, list):
                items = [item for item in response if isinstance(item, dict)]
            elif isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, list):
                    items = [item for item in data if isinstance(item, dict)]
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
        except CatalogServiceError:
            raise
        except Exception:
            raise CatalogServiceError("文本库目录加载异常")

    def fetch_text_by_id(self, text_id: str) -> str | None:
        try:
            url = f"{self._base_url}/api/v1/texts/{text_id}"
            response = self._api_client.request("GET", url)
            if response is None:
                raise CatalogServiceError("文本内容请求失败")
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, dict):
                    content = data.get("content")
                    return content if isinstance(content, str) else None
                return response.get("content")
            return None
        except CatalogServiceError:
            raise
        except Exception:
            raise CatalogServiceError("文本内容加载异常")
