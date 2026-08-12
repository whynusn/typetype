"""OTT Core v1 client helpers.

This client owns protocol routing between the Service Profile (`/ott/v1`) and
the Static Profile. Caching and HTTP transport stay in OttTextProvider for
now so this can be introduced without changing the persistence model.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from urllib.parse import urlencode

from .ott_normalization import normalize_source, normalize_summary, redact_url, safe_int
from ..utils.logger import log_warning

FetchJson = Callable[[str, str, str | None, int], dict | None]
FetchText = Callable[[str, str, str | None, int], str | None]

DEFAULT_STATIC_SEGMENT_SIZE = 1000


class OttClient:
    """Read-only OTT Core v1 client."""

    def __init__(
        self,
        primary_url: str,
        mirror_url: str,
        authority: str,
        fetch_json: FetchJson,
        fetch_text: FetchText,
        max_content_bytes: int,
    ) -> None:
        self._primary_url = primary_url.rstrip("/")
        self._mirror_url = mirror_url.rstrip("/")
        self._authority = authority
        self._fetch_json = fetch_json
        self._fetch_text = fetch_text
        self._max_content_bytes = max_content_bytes

    def list_entries(self) -> list[dict] | None:
        for base_url in self._profile_base_urls():
            service = self._list_service_entries(base_url)
            if service is not None:
                return service
            static = self._list_static_entries(base_url)
            if static is not None:
                return static
        return None

    def list_sources(self) -> list[dict] | None:
        for base_url in self._profile_base_urls():
            service = self._list_service_sources(base_url)
            if service is not None:
                return service
            static = self._list_static_sources(base_url)
            if static is not None:
                return static
        return None

    def get_entry(self, entry_id: str) -> dict | None:
        for base_url in self._profile_base_urls():
            service = self._get_service_entry(base_url, entry_id)
            if service is not None:
                return service
            static = self._get_static_entry(base_url, entry_id)
            if static is not None:
                return static
        return None

    def get_segment(
        self,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size_hint: int = DEFAULT_STATIC_SEGMENT_SIZE,
    ) -> dict | None:
        for base_url in self._profile_base_urls():
            service = self._get_service_segment(
                base_url, entry_id, revision_id, segment_index
            )
            if service is not None:
                return service
            static = self._get_static_segment(
                base_url,
                entry_id,
                revision_id,
                segment_index,
                segment_size_hint,
            )
            if static is not None:
                return static
        return None

    def _profile_base_urls(self) -> list[str]:
        urls = [self._primary_url] if self._primary_url else []
        if self._mirror_url and self._mirror_url not in urls:
            urls.append(self._mirror_url)
        return urls

    def _list_service_entries(self, base_url: str) -> list[dict] | None:
        result: list[dict] = []
        page = 1
        limit = 200
        max_pages = 20
        while page <= max_pages:
            query = urlencode({"page": page, "limit": limit})
            data = self._fetch_json(
                f"ott/service/entries/{page}",
                f"{base_url}/ott/v1/entries?{query}",
                None,
                self._max_content_bytes,
            )
            if data is None:
                # 任一页失败 → 整列表视为失败，不得把半截列表当完整结果
                log_warning(
                    f"[OttClient] 分页中断: {redact_url(base_url)} 第 {page} 页请求失败"
                )
                return None
            raw = data.get("entries", [])
            if not isinstance(raw, list):
                log_warning(
                    f"[OttClient] 分页响应非法: {redact_url(base_url)} 第 {page} 页 entries 非列表"
                )
                return None
            result.extend(
                normalize_summary(e, self._authority)
                for e in raw
                if isinstance(e, dict)
            )
            pages = safe_int(data.get("pages"), page)
            if page >= pages or not raw:
                break
            page += 1
        return result

    def _list_static_entries(self, base_url: str) -> list[dict] | None:
        data = self._fetch_json(
            "ott/static/entries",
            f"{base_url}/entries.json",
            None,
            self._max_content_bytes,
        )
        if data is None:
            return None
        raw = data.get("entries", [])
        if not isinstance(raw, list):
            return None
        return [
            normalize_summary(e, self._authority) for e in raw if isinstance(e, dict)
        ]

    def _list_service_sources(self, base_url: str) -> list[dict] | None:
        data = self._fetch_json(
            "ott/service/sources",
            f"{base_url}/ott/v1/sources",
            None,
            self._max_content_bytes,
        )
        if data is None:
            return None
        raw = data.get("sources", [])
        if not isinstance(raw, list):
            return None
        return [normalize_source(e) for e in raw if isinstance(e, dict)]

    def _list_static_sources(self, base_url: str) -> list[dict] | None:
        data = self._fetch_json(
            "ott/static/sources",
            f"{base_url}/sources.json",
            None,
            self._max_content_bytes,
        )
        if data is None:
            return None
        raw = data.get("sources", [])
        if not isinstance(raw, list):
            return None
        return [normalize_source(e) for e in raw if isinstance(e, dict)]

    def _get_service_entry(self, base_url: str, entry_id: str) -> dict | None:
        return self._fetch_json(
            f"ott/service/entry/{entry_id}",
            f"{base_url}/ott/v1/entries/{entry_id}",
            None,
            self._max_content_bytes,
        )

    def _get_static_entry(self, base_url: str, entry_id: str) -> dict | None:
        return self._fetch_json(
            f"ott/static/entry/{entry_id}",
            f"{base_url}/entries/{entry_id}.json",
            None,
            self._max_content_bytes,
        )

    def _get_service_segment(
        self, base_url: str, entry_id: str, revision_id: str, segment_index: int
    ) -> dict | None:
        return self._fetch_json(
            f"ott/service/segments/{entry_id}/{revision_id}/{segment_index}",
            (
                f"{base_url}/ott/v1/entries/{entry_id}"
                f"/revisions/{revision_id}/segments/{segment_index}"
            ),
            None,
            self._max_content_bytes,
        )

    def _get_static_segment(
        self,
        base_url: str,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size_hint: int,
    ) -> dict | None:
        content = self._fetch_text(
            f"ott/static/segments/{entry_id}/{revision_id}/{segment_index}",
            f"{base_url}/segments/{revision_id}/{segment_index}.txt",
            None,
            self._max_content_bytes,
        )
        if content is None:
            return None
        segment_size = max(1, segment_size_hint)
        start = (segment_index - 1) * segment_size
        return {
            "entry_id": entry_id,
            "revision_id": revision_id,
            "index": segment_index,
            "start_char": start,
            "end_char": start + len(content),
            "char_count": len(content),
            "content_hash": "sha256:"
            + hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }
