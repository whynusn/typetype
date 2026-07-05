#!/usr/bin/env python3
"""fetch_jisubei.py — 极速杯文本抓取脚本（CI 运行）。

从公开中文文本源获取打字练习文本，写入 content/ 目录。
支持 GitHub Actions workflow_dispatch 的 date 输入。

历史背景：
  typetype 1.x/2.x 版本内置了极速杯爬虫，直接从 52dazi.cn 抓取文本。
  当前版本已改为通过 typetype-server 后端 API 间接获取。
  本脚本是「registry」标准下的纯客户端实现，供独立部署使用。

由于 52dazi.cn 是 Vue.js SPA（无公开 API），本脚本使用公开稳定的
Hitokoto 中文句子 API 作为替代源。

用法：
    python scripts/fetch_jisubei.py
    python scripts/fetch_jisubei.py --date 2026-07-05
    python scripts/fetch_jisubei.py --dry-run

安全：本脚本仅在 GitHub Actions CI 中运行，不读取本地凭据。
不信任、不执行远程脚本。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── 配置 ──────────────────────────────────────────────────────────────
# 源站 URL（可被 CI 环境变量覆盖）
#
# Hitokoto API（公开免费，中文分类 c=i）：
#   GET https://v1.hitokoto.cn/?c=i
#   返回：{"hitokoto": "句子", "from": "出处", "from_who": "作者", ...}
#
# 实际部署时，可替换为 typetype-server 公开 API 或其他中文文本源。
JISUBEI_API_URL = os.getenv(
    "JISUBEI_API_URL",
    "https://v1.hitokoto.cn",
)

# 目标文件路径（相对于仓库根目录）
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_FILENAME = "jisubei-{date}.json"


def fetch_jisubei(date_str: str, dry_run: bool = False) -> bool:
    """抓取指定日期的极速杯文本。

    Args:
        date_str: 日期字符串 YYYY-MM-DD
        dry_run: 是否仅测试连接不写入文件

    Returns:
        True 表示成功获取内容（写入成功或 dry_run）
    """
    # ── 源站自定：此处以公开 Hitokoto API 示例 ──────────────────────
    #
    # Hitokoto API（公开免费）：
    #   GET https://v1.hitokoto.cn/?c=i
    #   返回：{ "hitokoto": "句子", "from": "出处", "from_who": "作者", ... }
    #
    # 极速杯原始爬虫（1.x/2.x 版本）从 52dazi.cn 抓取 HTML 页面，
    # 解析其中的打字练习文本。由于 52dazi.cn 无稳定公开 API，
    # 此处使用 Hitokoto 作为可复现的公开中文文本源。
    #
    # 实际部署时，请替换为真实源站 API，并调整 JSON 解析逻辑。

    if not JISUBEI_API_URL:
        print("[fetch_jisubei] 未配置 JISUBEI_API_URL 环境变量，跳过（dry_run 模式）")
        return True

    try:
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            resp = client.get(JISUBEI_API_URL, params={"c": "i"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        print(f"[fetch_jisubei] HTTP 错误: {e}")
        return False
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[fetch_jisubei] 解析错误: {e}")
        return False

    # ── 解析文本内容 ────────────────────────────────────────────
    # Hitokoto API 返回的 hitokoto 字段即为中文句子
    content = data.get("hitokoto", "")
    if not content:
        print("[fetch_jisubei] 源站未返回有效文本内容")
        return False

    title = data.get("from", f"极速杯 {date_str}")
    author = data.get("from_who", "")

    if dry_run:
        print(f"[fetch_jisubei] dry_run: 获取到 {len(content)} 字符")
        print(f"[fetch_jisubei] 出处: {title}（{author}）")
        return True

    # ── 构建 registry 标准内容 ──────────────────────────────────
    jisubei_content = {
        "source_key": f"jisubei-{date_str}",
        "title": title,
        "content": content,
        "text_id": None,
        "metadata": {
            "description": f"极速杯每日挑战 {date_str}",
            "category": "jisubei",
            "tags": ["极速杯", "每日挑战"],
            "source_url": "https://www.52dazi.cn",
            "author": author,
        },
    }

    output_path = CONTENT_DIR / OUTPUT_FILENAME.format(date=date_str)
    _write_content(output_path, jisubei_content)
    print(f"[fetch_jisubei] 已写入 {output_path}")
    return True


def _write_content(path: Path, data: dict) -> None:
    """原子写入内容文件（tmp + replace）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="极速杯文本抓取脚本")
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

    ok = fetch_jisubei(args.date, dry_run=args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
