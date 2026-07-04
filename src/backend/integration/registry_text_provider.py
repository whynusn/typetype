"""注册表文本提供器 - 从 CDN 注册表获取文本。

实现 TextProvider Protocol。动态文本通过 GitHub Actions CI 生成并推送至静态仓库，
客户端只读不写，不执行远程脚本。
"""

from pathlib import Path

import httpx

from ..config.runtime_config import RegistryConfig
from ..models.dto.fetched_text import FetchedText
from ..models.dto.text_catalog_item import TextCatalogItem


class RegistryTextProvider:
    """注册表文本提供器，实现 TextProvider 协议。"""

    def __init__(
        self,
        config: RegistryConfig,
        cache_dir: Path,
        http_client: httpx.Client | None = None,
    ):
        self._config = config
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_catalog(self) -> list[TextCatalogItem]:
        data = self._fetch_registry_index()
        if data is None:
            return []
        sources = data.get("sources", [])
        if not isinstance(sources, list):
            return []
        return [
            TextCatalogItem(
                id=item.get("id", 0),
                source_key=item["source_key"],
                label=item.get("label", item["source_key"]),
                description=item.get("description", ""),
                has_ranking=bool(item.get("has_ranking", False)),
            )
            for item in sources
            if isinstance(item, dict) and item.get("source_key")
        ]

    def fetch_text_by_key(self, source_key: str) -> FetchedText | None:
        if not self._validate_source_key(source_key):
            return None
        data = self._fetch_content(source_key)
        if data is None:
            return None
        content = data.get("content", "")
        if not isinstance(content, str) or not content:
            return None
        content = self._sanitize_content(content)
        return FetchedText(
            content=content,
            text_id=data.get("text_id"),
            title=data.get("title", "") if isinstance(data.get("title"), str) else "",
        )

    def fetch_text_by_client_id(self, client_text_id: int) -> FetchedText | None:
        return None

    def _fetch_registry_index(self) -> dict | None:
        url = f"{self._config.primary_url}/registry_index.json"
        data = self._fetch_json(url)
        if data is None and self._config.mirror_url:
            url = f"{self._config.mirror_url}/registry_index.json"
            data = self._fetch_json(url)
        return data

    def _fetch_content(self, source_key: str) -> dict | None:
        url = f"{self._config.primary_url}/content/{source_key}.json"
        data = self._fetch_json(url, max_bytes=self._config.max_content_bytes)
        if data is None and self._config.mirror_url:
            url = f"{self._config.mirror_url}/content/{source_key}.json"
            data = self._fetch_json(url, max_bytes=self._config.max_content_bytes)
        return data

    def _fetch_json(self, url: str, max_bytes: int = 0) -> dict | None:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            if max_bytes > 0 and len(response.content) > max_bytes:
                return None
            return response.json()
        except httpx.HTTPError:
            return None
        except (ValueError, TypeError, OSError):
            return None

    @staticmethod
    def _validate_source_key(key: str) -> bool:
        return bool(key) and "/" not in key and ".." not in key and "\\" not in key

    @staticmethod
    def _sanitize_content(content: str) -> str:
        return "".join(c for c in content if c >= " " or c in "\n\r\t")
