from __future__ import annotations

from ..models.dto.text_catalog_item import TextCatalogItem
from .ott_normalization import safe_int


def catalog_items_from_sources(sources: list[dict]) -> list[TextCatalogItem]:
    result: list[TextCatalogItem] = []
    for index, item in enumerate(sources):
        if not isinstance(item, dict) or not item.get("source_key"):
            continue
        char_count = item.get("char_count", item.get("charCount", 0))
        item_id = safe_int(item.get("id"), -1)
        result.append(
            TextCatalogItem(
                id=item_id if item_id > 0 else index + 1,
                source_key=str(item["source_key"]),
                label=str(item.get("label", item["source_key"]) or item["source_key"]),
                description=str(item.get("description", "") or ""),
                charCount=safe_int(char_count),
                category=str(item.get("category", "") or ""),
                update_freq=str(item.get("update_freq", "") or ""),
            )
        )
    return result
