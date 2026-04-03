from typing import TYPE_CHECKING, Any, Callable

from config.text_source_config import TextCatalogItem
from ...infrastructure.network_errors import CatalogServiceError

if TYPE_CHECKING:
    from ...infrastructure.api_client import ApiClient


class RemoteTextProvider:
    def __init__(
        self,
        base_url: str,
        api_client: "ApiClient",
        token_provider: Callable[[], str] | None = None,
    ):
        self._base_url = base_url
        self._api_client = api_client
        self._token_provider = token_provider

    def _get_auth_headers(self) -> dict[str, str]:
        if self._token_provider:
            token = self._token_provider()
            if token:
                return {"Authorization": f"Bearer {token}"}
        return {}

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
                    text_id=item.get("sourceKey", ""),
                    label=item.get("label", ""),
                    description=item.get("category", ""),
                    has_ranking=False,
                )
                for item in items
            ]
        except CatalogServiceError:
            raise
        except Exception:
            raise CatalogServiceError("文本库目录加载异常")

    def fetch_text_by_key(self, source_key: str) -> str | None:
        try:
            url = f"{self._base_url}/api/v1/texts/latest/{source_key}"
            response = self._api_client.request(
                "GET", url, headers=self._get_auth_headers()
            )
            if response is None:
                return None
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, dict):
                    content = data.get("content")
                    return content if isinstance(content, str) else None
            return None
        except Exception:
            return None
