#!/usr/bin/env python3
"""fetch_jisubei.py — 极速杯文本抓取脚本（CI 运行）。

从赛文（SaiWen）API 获取每日打字文本，写入 content/ 目录。
赛文 API 从 52dazi.cn 抓取原始内容，本脚本逆向其加密协议。

历史背景：
  typetype 1.x 版本内置了本爬虫（GetSaiWen.py + Crypt.py），
  直接从赛文 API 获取文本。当前版本改为通过 typetype-server 间接获取。
  本脚本是 registry 标准下的移植版本，与原始 1.x 实现完全兼容。

加密协议：AES-CBC / ZeroPadding / Latin1 / Base64
API 地址：https://www.jsxiaoshi.com/index.php/Api/Text/getContent

用法：
    python scripts/fetch_jisubei.py
    python scripts/fetch_jisubei.py --date 2026-07-05
    python scripts/fetch_jisubei.py --dry-run

依赖：pypycryptodome（CI workflow 中 pip install）
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from Crypto.Cipher import AES

# ── 赛文 API 配置 ────────────────────────────────────────────────────
SAIWEN_API_URL = os.getenv(
    "SAIWEN_API_URL",
    "https://www.jsxiaoshi.com/index.php/Api/Text/getContent",
)

# 目标文件路径（相对于仓库根目录）
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
OUTPUT_FILENAME = "jisubei-{date}.json"

# ── 加密参数（与 1.x Crypt.py 完全一致）──────────────────────────────
KEY = b"c9ec834c80f77237"
IV = b"db4d6bfde3057dca"
BLOCK_SIZE = 16


def _zero_pad(data: bytes) -> bytes:
    """ZeroPadding：用零填充到块大小的倍数。"""
    remainder = len(data) % BLOCK_SIZE
    if remainder == 0:
        return data
    return data + b"\x00" * (BLOCK_SIZE - remainder)


def _encrypt(data: dict) -> str:
    """加密数据字典为 Base64 字符串。

    与 typetype 1.x Crypt.py 的 encrypt() 完全兼容。
    """
    raw = json.dumps(data, ensure_ascii=False).encode("latin-1")
    padded = _zero_pad(raw)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")


# ── 爬虫逻辑 ─────────────────────────────────────────────────────────


def fetch_jisubei(date_str: str, dry_run: bool = False) -> bool:
    """抓取当日极速杯文本。

    Args:
        date_str: 日期字符串 YYYY-MM-DD（用于输出文件名）
        dry_run: 是否仅测试连接不写入文件

    Returns:
        True 表示成功获取内容
    """
    # 构造赛文 API 请求体（与 1.x GetSaiWen.py 完全一致）
    payload_data = {
        "competitionType": 0,
        "snumflag": "1",
        "from": "web",
        "timestamp": int(time.time()),
        "version": "v2.1.5",
        "subversions": 17108,
    }

    encrypted = _encrypt(payload_data)
    post_payload = {"0": encrypted[1:]}  # 去掉首字符

    try:
        with httpx.Client(timeout=20.0, trust_env=False) as client:
            resp = client.post(SAIWEN_API_URL, json=post_payload)
            resp.raise_for_status()
            res_data = resp.json()
    except httpx.HTTPError as e:
        print(f"[fetch_jisubei] HTTP 错误: {e}")
        return False
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[fetch_jisubei] 解析错误: {e}")
        return False

    # 解析响应（与 1.x 响应解析逻辑一致）
    msg = res_data.get("msg")
    content = ""
    title = ""

    if isinstance(msg, str):
        content = msg
        title = "极速杯"
    elif isinstance(msg, dict):
        # msg["0"] 是文本内容，msg["a_name"] 是标题
        if "0" in msg:
            content = str(msg["0"])
        if "a_name" in msg:
            title = str(msg["a_name"])
        # 备选：msg["content"] 有时也包含内容
        if not content and "content" in msg:
            content = str(msg["content"])

    if not content:
        print("[fetch_jisubei] 源站未返回有效文本内容")
        print(f"[fetch_jisubei] 原始响应: {json.dumps(res_data, ensure_ascii=False)[:200]}")
        return False

    title = title or f"极速杯 {date_str}"

    if dry_run:
        print(f"[fetch_jisubei] dry_run: 获取到 {len(content)} 字符")
        print(f"[fetch_jisubei] 标题: {title}")
        print(f"[fetch_jisubei] 内容预览: {content[:50]}...")
        return True

    # 构建 registry 标准内容
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
    parser = argparse.ArgumentParser(description="极速杯文本抓取脚本（赛文 API）")
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
