from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse


def _script_authority(url: str) -> str:
    """脚本 authority：``script:{sha256(url)[:12]}``。

    以脚本 URL 指纹做命名空间，防不同脚本产出同 entry_id 被 dedupe 吞掉。
    与 ott-instance / ott-rule 命名空间隔离。
    """
    return f"script:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"


def _bridge_authority(endpoint: str) -> str:
    """桥接 authority：``bridge:{sha256(endpoint)[:12]}``。

    以 bridge endpoint 指纹做命名空间，防不同桥接源产出同 entry_id 被 dedupe
    吞掉。与 ott-instance / ott-rule / ott-script 命名空间隔离。
    """
    return f"bridge:{hashlib.sha256(endpoint.encode('utf-8')).hexdigest()[:12]}"


def local_path_from_file_uri(url: str) -> Path:
    """将 file:// URI 转为本地路径（兼容 Windows 盘符）。"""
    path = urlparse(url).path
    if len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
        path = path[1:]
    return Path(path)


def redact_url(url: str) -> str:
    """日志脱敏：仅保留 scheme://host，丢弃路径与查询参数。"""
    try:
        parsed = urlparse(url)
    except (ValueError, OSError):
        return "<invalid-url>"
    if not parsed.scheme or not parsed.hostname:
        return "<invalid-url>"
    return f"{parsed.scheme}://{parsed.hostname}"


def safe_int(value: str | int | bool | None, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def normalize_summary(entry: dict, authority: str) -> dict:
    char_count = safe_int(entry.get("char_count", entry.get("charCount", 0)))
    return {
        "entry_id": str(entry.get("entry_id", "") or ""),
        "title": str(entry.get("title", "") or ""),
        "preview": str(entry.get("preview", "") or ""),
        "source_key": str(entry.get("source_key", "") or ""),
        "source_label": str(entry.get("source_label", "") or ""),
        "charCount": char_count,
        "char_count": char_count,
        "fetched_at": str(entry.get("fetched_at", entry.get("updated_at", "")) or ""),
        "category": str(entry.get("category", "") or ""),
        "tags": entry.get("tags", [])
        if isinstance(entry.get("tags", []), list)
        else [],
        "content_mode": str(entry.get("content_mode", "inline") or "inline"),
        "current_revision_id": str(entry.get("current_revision_id", "") or ""),
        "segment_count": safe_int(entry.get("segment_count")),
        "segment_size_hint": safe_int(entry.get("segment_size_hint")),
        "authority": str(entry.get("authority", authority) or authority),
    }


def normalize_source(source: dict) -> dict:
    char_count = safe_int(source.get("char_count", source.get("charCount", 0)))
    return {
        "id": safe_int(source.get("id")),
        "source_key": str(source.get("source_key", "") or ""),
        "label": str(source.get("label", source.get("source_key", "")) or ""),
        "description": str(source.get("description", "") or ""),
        "char_count": char_count,
        "charCount": char_count,
        "category": str(source.get("category", "") or ""),
        "update_freq": str(source.get("update_freq", "") or ""),
        "entry_count": safe_int(source.get("entry_count")),
        "tags": source.get("tags", [])
        if isinstance(source.get("tags", []), list)
        else [],
        "rights_summary": str(source.get("rights_summary", "") or ""),
        "updated_at": str(source.get("updated_at", "") or ""),
    }
