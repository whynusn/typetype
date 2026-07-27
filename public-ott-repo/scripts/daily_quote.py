"""daily_quote.py - 每日一言脚本源（ott-script 示例）。

从多个公开 API 获取每日文本，合并返回。
脚本必须定义 fetch_entries() -> list[dict]。
"""

import hashlib
import json
import time

import httpx


def fetch_entries():
    """获取每日文本条目。"""
    entries = []

    # 源 1：Hitokoto 一言
    try:
        resp = httpx.get("https://v1.hitokoto.cn/?c=i", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        entries.append({
            "entry_id": f"hitokoto-{int(time.time()) // 3600}",
            "title": data.get("from", "一言"),
            "content": data.get("hitokoto", ""),
            "source_label": "一言",
            "tags": ["quote", "chinese"],
            "revision_id": "v1",
        })
    except Exception:
        pass

    # 源 2：今日诗词（公开 API）
    try:
        resp = httpx.get("https://v1.jinrishici.com/all.json", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        if content:
            entry_id = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            entries.append({
                "entry_id": f"jinrishici-{entry_id}",
                "title": f"今日诗词 - {data.get('origin', '未知')}",
                "content": content,
                "source_label": "今日诗词",
                "tags": ["poetry", "daily"],
                "revision_id": "v1",
            })
    except Exception:
        pass

    # 源 3：英文名言
    try:
        resp = httpx.get("https://api.quotable.io/random?tags=inspirational", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        if content:
            entries.append({
                "entry_id": f"quotable-{data.get('_id', 'x')}",
                "title": f"Quote - {data.get('author', 'Unknown')}",
                "content": content,
                "source_label": "Quotable",
                "tags": ["quote", "english"],
                "revision_id": "v1",
            })
    except Exception:
        pass

    return entries
