from typing import TYPE_CHECKING, Any, Callable

from ..infrastructure.network_errors import CatalogServiceError
from ..models.dto.fetched_text import FetchedText
from ..models.dto.text_catalog_item import TextCatalogItem

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


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

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url。"""
        self._base_url = new_base_url

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
                    id=int(item.get("id", 0)),
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

    def fetch_text_by_key(self, source_key: str) -> FetchedText | None:
        """从服务器获取文本。

        Returns:
            FetchedText: 包含 id、content、title 的文本对象
            None: 请求失败时返回
        """
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
                    if not isinstance(content, str):
                        return None
                    text_id = data.get("id")
                    title = data.get("title", "")
                    return FetchedText(
                        content=content,
                        text_id=int(text_id) if text_id is not None else None,
                        title=title if isinstance(title, str) else "",
                    )
            return None
        except Exception:
            return None

    def fetch_text_by_client_id(self, client_text_id: int) -> FetchedText | None:
        """通过 clientTextId 从服务器查找文本。

        Returns:
            FetchedText: 包含 id 的文本对象（内容不重要，只需要 id）
            None: 未找到时返回
        """
        try:
            url = f"{self._base_url}/api/v1/texts/by-client-text-id/{client_text_id}"
            response = self._api_client.request(
                "GET", url, headers=self._get_auth_headers()
            )
            if response is None:
                return None
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, dict):
                    text_id = data.get("id")
                    if text_id is not None:
                        return FetchedText(
                            content=data.get("content", ""),
                            text_id=int(text_id),
                            title=data.get("title", ""),
                        )
            return None
        except Exception:
            return None
