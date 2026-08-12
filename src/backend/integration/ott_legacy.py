from __future__ import annotations

from collections.abc import Callable


def legacy_static_entries(
    registry_data: dict,
    fetch_content: Callable[[str], dict | None],
    sanitize_content: Callable[[str], str],
    authority: str,
) -> list[dict]:
    sources = registry_data.get("sources", [])
    if not isinstance(sources, list):
        return []
    result: list[dict] = []
    for item in sources:
        if not isinstance(item, dict) or not item.get("source_key"):
            continue
        source_key = str(item.get("source_key", "") or "")
        content_data = fetch_content(source_key)
        if content_data is None:
            continue
        source_label = str(item.get("label", source_key) or source_key)
        raw = content_data.get("entries", [])
        if not isinstance(raw, list) or not raw:
            raw = [
                {
                    "title": content_data.get("title", source_label),
                    "content": content_data.get("content", ""),
                    "fetched_at": content_data.get("fetched_at", ""),
                    "metadata": content_data.get("metadata", {}),
                }
            ]
        result.extend(
            {
                "entry_id": "",
                "title": str(entry.get("title", "") or source_label),
                "content": sanitize_content(str(entry.get("content", ""))),
                "source_key": source_key,
                "source_label": source_label,
                "charCount": len(str(entry.get("content", "") or "")),
                "char_count": len(str(entry.get("content", "") or "")),
                "fetched_at": str(entry.get("fetched_at", "")),
                "category": str(item.get("category", "")),
                "content_mode": "inline",
                "authority": authority,
            }
            for entry in raw
            if isinstance(entry, dict) and entry.get("content")
        )
    return result
