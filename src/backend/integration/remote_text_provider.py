from typing import TYPE_CHECKING, Any

from src.backend.security.secure_storage import SecureStorage

from ..infrastructure.network_errors import CatalogServiceError
from ..models.config.text_source_config import TextCatalogItem
from ..models.entity.text import Text

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class RemoteTextProvider:
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
            jwt = SecureStorage.get_jwt("current_user")
            url = f"{self._base_url}/api/v1/texts/latest/{source_key}"
            response = self._api_client.request(
                "GET", url, headers={"Authorization": f"Bearer {jwt}"}
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

    def fetch_text_entity(self, text_id: str) -> Text | None:
        response = self._fetch_raw(text_id)
        if response is None:
            return None
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            return None
        content = data.get("content")
        if not isinstance(content, str):
            return None
        return Text(
            id=data.get("id", 0),
            source_id=data.get("sourceId", 0),
            title=data.get("title", ""),
            content=content,
            char_count=data.get("charCount", 0),
            difficulty=data.get("difficulty", 0),
        )

    def fetch_text_by_id(self, text_id: str) -> str | None:
        text = self.fetch_text_entity(text_id)
        return text.content if text else None

    def _fetch_raw(self, text_id: str) -> dict[str, Any] | None:
        try:
            jwt = SecureStorage.get_jwt("current_user")
            url = f"{self._base_url}/api/v1/texts/{text_id}"
            response = self._api_client.request(
                "GET", url, headers={"Authorization": f"Bearer {jwt}"}
            )
            if response is None:
                raise CatalogServiceError("文本内容请求失败")
            if isinstance(response, dict):
                return response
            return None
        except CatalogServiceError:
            raise
        except Exception:
            raise CatalogServiceError("文本内容加载异常")
