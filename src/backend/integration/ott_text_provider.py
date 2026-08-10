from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from ..config.runtime_config import RegistryConfig
from ..models.dto.fetched_text import FetchedText
from ..models.dto.text_catalog_item import TextCatalogItem
from .ott_cached_fetcher import OttCachedFetcher
from .ott_catalog import catalog_items_from_sources
from .ott_client import OttClient
from .ott_legacy import legacy_static_entries
from .ott_normalization import safe_int

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor


class OttTextProvider:
    """OTT Core v1 文本提供器，实现 TextProvider 协议。"""

    def __init__(
        self,
        config: RegistryConfig,
        cache_dir: Path,
        http_client: httpx.Client | None = None,
        async_executor: AsyncExecutor | None = None,
    ) -> None:
        self._config = config
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client or httpx.Client(timeout=10.0, follow_redirects=False)
        self._cache = OttCachedFetcher(
            self._config,
            self._cache_dir,
            self._client,
            async_executor,
        )
        self._ott_client = OttClient(
            primary_url=self._config.primary_url,
            mirror_url=self._config.mirror_url,
            authority=self.authority,
            fetch_json=self._fetch_json_with_cache,
            fetch_text=self._fetch_text_with_cache,
            max_content_bytes=self._config.max_content_bytes,
        )

    def get_catalog(self) -> list[TextCatalogItem]:
        sources = self._fetch_ott_sources()
        if sources is None:
            sources = self._fetch_legacy_sources()
        return catalog_items_from_sources(sources)

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
        # 新格式：metadata 可能包含 title/description
        title = data.get("title", "")
        if not isinstance(title, str):
            title = ""
        if not title:
            metadata = data.get("metadata")
            if isinstance(metadata, dict):
                title = str(metadata.get("title", "") or "")
        # 提取 entries 数组（OTT v1+ 多条目格式）
        entries: list[dict] = []
        raw_entries = data.get("entries", [])
        if isinstance(raw_entries, list):
            for e in raw_entries:
                if isinstance(e, dict) and e.get("content"):
                    entries.append(
                        {
                            "title": e.get("title", ""),
                            "content": self._sanitize_content(str(e["content"])),
                            "fetched_at": e.get("fetched_at", ""),
                        }
                    )
        return FetchedText(
            content=content,
            text_id=data.get("text_id"),
            title=title,
            entries=entries,
        )

    def fetch_text_by_client_id(self, client_text_id: int) -> FetchedText | None:
        return None

    def fetch_all_entries(self) -> list[dict]:
        entries = self._fetch_ott_entry_summaries()
        if entries is not None:
            return entries

        return self._fetch_legacy_static_entries()

    def _fetch_legacy_static_entries(self) -> list[dict]:
        data = self._fetch_registry_index()
        if data is None:
            return []
        return legacy_static_entries(
            data,
            self._fetch_content,
            self._sanitize_content,
            self.authority,
        )

    def fetch_text_by_entry_id(self, entry_id: str) -> FetchedText | None:
        if not self._validate_identifier(entry_id):
            return None
        data = self._fetch_ott_entry_detail(entry_id)
        if data is None:
            return None
        if not self._looks_like_ott_entry_detail(data):
            return None
        mode = str(data.get("content_mode") or "inline")
        content = data.get("content", "")
        if not isinstance(content, str):
            content = ""
        if mode == "inline" and not content:
            return None
        return FetchedText(
            content=self._sanitize_content(content),
            title=str(data.get("title", "") or ""),
            source_key=str(data.get("source_key", "") or ""),
            entry_id=str(data.get("entry_id", entry_id) or entry_id),
            revision_id=str(
                data.get("current_revision_id") or data.get("revision_id") or ""
            ),
            content_hash=str(data.get("content_hash", "") or ""),
            content_mode=mode,
            segment_count=safe_int(data.get("segment_count")),
            segment_size_hint=safe_int(data.get("segment_size_hint")),
        )

    def fetch_ott_segment(
        self,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        source_segment_size: int = 1000,
    ) -> dict | None:
        if (
            not self._validate_identifier(entry_id)
            or not self._validate_identifier(revision_id)
            or segment_index < 1
        ):
            return None
        data = self._ott_client.get_segment(
            entry_id,
            revision_id,
            segment_index,
            max(1, source_segment_size),
        )
        if data is None:
            return None
        content = data.get("content", "")
        if not isinstance(content, str):
            return None
        return {
            "entry_id": str(data.get("entry_id", entry_id) or entry_id),
            "revision_id": str(data.get("revision_id", revision_id) or revision_id),
            "index": safe_int(data.get("index"), segment_index),
            "start_char": safe_int(data.get("start_char")),
            "end_char": safe_int(data.get("end_char")),
            "char_count": safe_int(data.get("char_count"), len(content)),
            "content_hash": str(data.get("content_hash", "") or ""),
            "content": self._sanitize_content(content),
        }

    # ------------------------------------------------------------------
    # 网络获取（含缓存决策）
    # ------------------------------------------------------------------

    def _fetch_registry_index(self) -> dict | None:
        url = f"{self._config.primary_url}/registry_index.json"
        mirror_url = (
            f"{self._config.mirror_url}/registry_index.json"
            if self._config.mirror_url
            else None
        )
        return self._fetch_json_with_cache(
            cache_key="index", url=url, mirror_url=mirror_url
        )

    def _fetch_content(self, source_key: str) -> dict | None:
        url = f"{self._config.primary_url}/content/{source_key}.json"
        mirror_url = (
            f"{self._config.mirror_url}/content/{source_key}.json"
            if self._config.mirror_url
            else None
        )
        return self._fetch_json_with_cache(
            cache_key=f"content/{source_key}",
            url=url,
            mirror_url=mirror_url,
            max_bytes=self._config.max_content_bytes,
        )

    def _fetch_ott_entry_summaries(self) -> list[dict] | None:
        return self._ott_client.list_entries()

    def _fetch_ott_sources(self) -> list[dict] | None:
        return self._ott_client.list_sources()

    def _fetch_ott_entry_detail(self, entry_id: str) -> dict | None:
        return self._ott_client.get_entry(entry_id)

    def _fetch_legacy_sources(self) -> list[dict]:
        data = self._fetch_registry_index()
        if data is None:
            return []
        sources = data.get("sources", [])
        if not isinstance(sources, list):
            return []
        return [item for item in sources if isinstance(item, dict)]

    def _fetch_json_with_cache(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None = None,
        max_bytes: int = 0,
    ) -> dict | None:
        return self._cache.fetch_json_with_cache(cache_key, url, mirror_url, max_bytes)

    def _fetch_text_with_cache(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None = None,
        max_bytes: int = 0,
    ) -> str | None:
        return self._cache.fetch_text_with_cache(cache_key, url, mirror_url, max_bytes)

    # ------------------------------------------------------------------
    # 缓存读写
    # ------------------------------------------------------------------

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache.cache_path(cache_key)

    def clear_cache(self) -> None:
        self._cache.clear_cache()

    def _read_cache(self, cache_key: str) -> dict | None:
        return self._cache.read_cache(cache_key)

    def _write_cache(self, cache_key: str, data: dict) -> None:
        self._cache.write_cache(cache_key, data)

    # ------------------------------------------------------------------
    # 安全与清洗
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_source_key(key: str) -> bool:
        return bool(key) and "/" not in key and ".." not in key and "\\" not in key

    @staticmethod
    def _validate_identifier(value: str) -> bool:
        return (
            bool(value) and "/" not in value and ".." not in value and "\\" not in value
        )

    @property
    def authority(self) -> str:
        parsed = urlparse(self._config.primary_url)
        return parsed.netloc or parsed.path.strip("/") or "local"

    @staticmethod
    def _sanitize_content(content: str) -> str:
        return "".join(c for c in content if c >= " " or c in "\n\r\t")

    @staticmethod
    def _looks_like_ott_entry_detail(data: dict) -> bool:
        return any(
            key in data
            for key in (
                "entry_id",
                "content_mode",
                "current_revision_id",
                "revision_id",
                "segment_count",
            )
        )
