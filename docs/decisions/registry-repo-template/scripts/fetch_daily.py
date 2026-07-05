#!/usr/bin/env python3
"""fetch_daily.py — 每日一文抓取脚本（CI 运行）。

从公开中文文本源获取当日的文章正文，写入 content/daily.json。
支持 GitHub Actions workflow_dispatch 的 date 输入。

用法：
    python scripts/fetch_daily.py
    python scripts/fetch_daily.py --date 2026-07-05
    python scripts/fetch_daily.py --dry-run

安全：本脚本仅在 GitHub Actions CI 中运行，不读取本地凭据。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── 配置 ──────────────────────────────────────────────────────────────
# 默认使用 Hitokoto 中文句子 API（公开免费）
DAILY_API_URL = os.getenv("DAILY_API_URL", "https://v1.hitokoto.cn")

# 目标文件路径（相对于仓库根目录）
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
DAILY_PATH = CONTENT_DIR / "daily.json"


def fetch_daily(date_str: str, dry_run: bool = False) -> bool:
    """抓取指定日期的每日一文。

    Args:
        date_str: 日期字符串 YYYY-MM-DD
        dry_run: 是否仅测试连接不写入文件

    Returns:
        True 表示成功获取内容（写入成功或 dry_run）
    """
    # ── 源站自定：此处以公开 Hitokoto API 示例 ────────────────────
    #
    # Hitokoto API（公开免费）：
    #   GET https://v1.hitokoto.cn/?c=i
    #   返回：{ "hitokoto": "句子", "from": "出处", "from_who": "作者", ... }

    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            resp = client.get(DAILY_API_URL, params={"c": "i"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        print(f"[fetch_daily] HTTP 错误: {e}")
        return False
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[fetch_daily] 解析错误: {e}")
        return False

    content = data.get("hitokoto", "")
    if not content:
        print("[fetch_daily] 源站未返回有效文本内容")
        return False

    if dry_run:
        print(f"[fetch_daily] dry_run: 获取到 {len(content)} 字符")
        return True

    # 写入内容文件
    daily_content = {
        "source_key": "daily",
        "content": content,
        "title": data.get("from", f"每日一文 {date_str}"),
        "text_id": None,
        "metadata": {
            "description": f"每日精选文章 {date_str}",
            "category": "daily",
            "tags": ["每日", "精选"],
        },
    }

    _write_content(DAILY_PATH, daily_content)
    print(f"[fetch_daily] 已写入 {DAILY_PATH}")
    return True


def _write_content(path: Path, data: dict) -> None:
    """原子写入内容文件（tmp + replace）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="每日一文抓取脚本")
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="目标日期 YYYY-MM-DD（默认今天）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅测试连接，不写入文件",
    )
    args = parser.parse_args()

    ok = fetch_daily(args.date, dry_run=args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
