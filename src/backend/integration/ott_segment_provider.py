from __future__ import annotations

from .ott_text_provider import OttTextProvider


class OttSegmentProvider:
    """TextSegmentProvider backed by OTT Core v1 server-defined segments."""

    def __init__(
        self,
        registry_provider: OttTextProvider,
        entry_id: str,
        revision_id: str,
        total_chars: int,
        source_segment_size: int = 1000,
    ) -> None:
        self._registry_provider = registry_provider
        self._entry_id = entry_id
        self._revision_id = revision_id
        self._total_chars = max(0, total_chars)
        self._source_segment_size = max(1, source_segment_size)
        self._cache: dict[int, dict] = {}

    def get_total_chars(self) -> int:
        return self._total_chars

    def get_segment(self, start: int, length: int) -> str:
        if start < 0 or length <= 0 or start >= self._total_chars:
            return ""
        end = min(self._total_chars, start + length)
        first = start // self._source_segment_size + 1
        last = (end - 1) // self._source_segment_size + 1
        parts = [
            str(self._server_segment(index).get("content", ""))
            for index in range(first, last + 1)
        ]
        combined = "".join(parts)
        offset = start - (first - 1) * self._source_segment_size
        return combined[offset : offset + (end - start)]

    def _server_segment(self, index: int) -> dict:
        cached = self._cache.get(index)
        if cached is not None:
            return cached
        segment = self._registry_provider.fetch_ott_segment(
            self._entry_id,
            self._revision_id,
            index,
        )
        if segment is None:
            raise RuntimeError(f"无法获取 OTT 分段: {index}")
        self._cache[index] = segment
        return segment
