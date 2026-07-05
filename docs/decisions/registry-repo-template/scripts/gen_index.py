#!/usr/bin/env python3
"""gen_index.py — 生成 registry_index.json（CI 运行）。

扫描 content/ 目录下的所有 JSON 文件，提取元数据，
生成 registry_index.json 的 sources 列表。

用法：
    python scripts/gen_index.py
"""

import json
import sys
from pathlib import Path

# 相对于仓库根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "content"
INDEX_PATH = ROOT_DIR / "registry_index.json"


def build_index() -> None:
    """扫描 content/ 目录，生成/更新 registry_index.json。"""
    sources = []

    for fpath in sorted(CONTENT_DIR.glob("*.json")):
        try:
            with fpath.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[gen_index] 跳过 {fpath.name}: {e}", file=sys.stderr)
            continue

        if not isinstance(data, dict):
            print(f"[gen_index] 跳过 {fpath.name}: 顶层不是 dict", file=sys.stderr)
            continue

        source_key = data.get("source_key")
        if not source_key:
            print(f"[gen_index] 跳过 {fpath.name}: 缺少 source_key", file=sys.stderr)
            continue

        # 构建索引条目
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        source = {
            "id": 0,
            "source_key": source_key,
            "label": data.get("title", source_key),
            "description": metadata.get("description", f"{source_key} 文本源"),
            "category": metadata.get("category", "static"),
            "update_freq": _infer_update_freq(source_key, fpath.name),
            "has_ranking": False,  # 结构兼容字段：registry 源恒为 SERVER_RESOLVED
        }
        sources.append(source)

    index = {
        "version": 1,
        "updated_at": _now_iso(),
        "sources": sources,
    }

    _write_index(INDEX_PATH, index)
    print(f"[gen_index] 已写入 {INDEX_PATH} ({len(sources)} 个源)")


def _infer_update_freq(source_key: str, filename: str) -> str:
    """根据 source_key 推断更新频率。"""
    if source_key == "daily" or source_key.startswith("jisubei-"):
        return "daily"
    return "static"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_index(path: Path, data: dict) -> None:
    """原子写入索引文件（tmp + replace）。"""
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


if __name__ == "__main__":
    build_index()
