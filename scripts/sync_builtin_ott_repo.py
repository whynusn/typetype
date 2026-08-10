#!/usr/bin/env python3
"""sync_builtin_ott_repo.py - 从独立官方内容仓生成内置离线 OTT Repo 快照。

官方默认内容仓：https://github.com/whynusn/typetype-default-ott-repo
本脚本把该仓的 static profile 复制到 resources/ott-repo，并把
authority/origin 改写成内置源标识，避免两处内容手抄漂移。

用法：
    uv run python scripts/sync_builtin_ott_repo.py
    uv run python scripts/sync_builtin_ott_repo.py --source ../typetype-default-ott-repo
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_DIR = ROOT / "resources" / "ott-repo"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _rewrite_origin(value):
    if isinstance(value, dict):
        if "origin" in value:
            value["origin"] = "typetype 内置"
        for child in value.values():
            _rewrite_origin(child)
    elif isinstance(value, list):
        for child in value:
            _rewrite_origin(child)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=str(ROOT.parent / "typetype-default-ott-repo"),
        help="独立官方内容仓本地 checkout 路径",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    source_manifest = source / "ott-repo.json"
    if not source_manifest.exists():
        parser.error(f"未找到官方内容仓 manifest: {source_manifest}")

    src_manifest = _load(source_manifest)

    shutil.rmtree(BUILTIN_DIR / "static", ignore_errors=True)
    shutil.copytree(source / "static", BUILTIN_DIR / "static")
    for rel in ("sources.json", "entries.json"):
        path = BUILTIN_DIR / "static" / rel
        data = _load(path)
        _rewrite_origin(data)
        _dump(path, data)
    for detail in (BUILTIN_DIR / "static" / "entries").glob("*.json"):
        data = _load(detail)
        _rewrite_origin(data)
        _dump(detail, data)

    ott = _load(BUILTIN_DIR / "static" / "ott.json")
    ott["authority_id"] = "typetype-builtin-static"
    ott.pop("repo_url", None)
    _dump(BUILTIN_DIR / "static" / "ott.json", ott)

    manifest = {
        "protocol": "ott-repo",
        "version": "1.0",
        "type": "repository",
        "repo_id": "typetype-builtin",
        "name": "TypeType 内置文本源",
        "description": "离线内置文本库（网络不可用时的 fallback）。",
        "maintainer": {"name": "typetype"},
        "license": "CC-BY-SA-4.0",
        "updated_at": src_manifest.get("updated_at", ""),
        "mirrors": [
            {"url": "file://__BUILTIN_DIR__/ott-repo.json", "priority": 1}
        ],
        "sources": [
            {
                "type": "ott-instance",
                "authority": "typetype-builtin-static",
                "label": "经典中文短句",
                "endpoints": [
                    {
                        "url": "file://__BUILTIN_DIR__/static/",
                        "profile": "static",
                        "priority": 1,
                    }
                ],
                "tags": ["chinese", "classic", "builtin"],
                "default_enabled": True,
            }
        ],
    }
    _dump(BUILTIN_DIR / "ott-repo.json", manifest)
    print(f"synced: {BUILTIN_DIR}")


if __name__ == "__main__":
    main()
