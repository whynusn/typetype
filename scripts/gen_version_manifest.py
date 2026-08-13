"""CI 生成并签名 version.json（ADR-014 影响段）。

用法：
    UPDATE_SIGNING_SECRET_KEY=<ed25519-hex> python scripts/gen_version_manifest.py \
        --version v0.5.0 \
        --assets \
    "typetype-linux-amd64.tar.gz=https://github.com/whynusn/typetype/releases/download/v0.5.0/typetype-linux-amd64.tar.gz,typetype-windows-amd64.zip=..." \
        --sha256 "typetype-linux-amd64.tar.gz=<sha256-hex>,typetype-windows-amd64.zip=..." \
        --out version.json

参数也支持环境变量回退：UPDATE_VERSION / UPDATE_ASSETS / UPDATE_SHA256 / UPDATE_OUT。

说明：
- sha256 由 CI 在构建完成后先计算好再传入（本脚本不下载、不计算文件哈希）。
- 签名对象为剔除 ``signature`` 键的 canonical JSON
  （sort_keys + ensure_ascii=False + 紧凑分隔符，与客户端验签一致）。
- 输出 ``{version, assets: [{name,url,sha256}], signature}``，signature 为
  裸 Ed25519 hex。
- 派生公钥 hex 打印到 stderr，供配置 UPDATE_SIGNING_PUBKEY。
- 私钥来自环境变量 UPDATE_SIGNING_SECRET_KEY（Ed25519 hex，32 字节）；
  缺失/非法则报错退出 1。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _load_private_key() -> Ed25519PrivateKey:
    raw = os.environ.get("UPDATE_SIGNING_SECRET_KEY", "").strip()
    if not raw:
        print(
            "错误：缺少环境变量 UPDATE_SIGNING_SECRET_KEY（Ed25519 私钥 hex）",
            file=sys.stderr,
        )
        sys.exit(1)
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    try:
        key_bytes = bytes.fromhex(raw)
    except ValueError:
        print("错误：UPDATE_SIGNING_SECRET_KEY 不是合法 hex", file=sys.stderr)
        sys.exit(1)
    if len(key_bytes) != 32:
        print(
            "错误：UPDATE_SIGNING_SECRET_KEY 长度应为 32 字节（64 个 hex 字符）",
            file=sys.stderr,
        )
        sys.exit(1)
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


def _parse_pairs(value: str) -> dict[str, str]:
    """解析 ``name=value,name=value`` 列表为 dict（value 含 ``=`` 取首个分隔）。"""
    result: dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            print(f"错误：无法解析 '{item}'（应为 name=value）", file=sys.stderr)
            sys.exit(1)
        name, _, val = item.partition("=")
        result[name.strip()] = val.strip()
    return result


def _canonical_bytes(manifest: dict) -> bytes:
    return json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成并签名 version.json")
    parser.add_argument("--version", help="发布版本（如 v0.5.0）")
    parser.add_argument("--assets", help="资产列表 name=url,name=url...")
    parser.add_argument("--sha256", help="资产 sha256 name=hash,name=hash...")
    parser.add_argument("--out", default="version.json", help="输出路径")
    args = parser.parse_args()

    version = args.version or os.environ.get("UPDATE_VERSION", "").strip()
    assets_raw = args.assets or os.environ.get("UPDATE_ASSETS", "").strip()
    sha256_raw = args.sha256 or os.environ.get("UPDATE_SHA256", "").strip()
    out = args.out or os.environ.get("UPDATE_OUT", "version.json")

    if not version:
        print("错误：必须提供 --version 或环境变量 UPDATE_VERSION", file=sys.stderr)
        sys.exit(1)
    if not assets_raw:
        print("错误：必须提供 --assets 或环境变量 UPDATE_ASSETS", file=sys.stderr)
        sys.exit(1)

    assets_map = _parse_pairs(assets_raw)
    sha256_map = _parse_pairs(sha256_raw) if sha256_raw else {}
    for name in assets_map:
        if not sha256_map.get(name):
            print(f"警告：资产 {name} 缺少 sha256，客户端下载将拒绝", file=sys.stderr)

    private_key = _load_private_key()
    manifest: dict = {
        "version": version,
        "assets": [
            {"name": name, "url": assets_map[name], "sha256": sha256_map.get(name, "")}
            for name in assets_map
        ],
    }
    signature = private_key.sign(_canonical_bytes(manifest)).hex()
    manifest["signature"] = signature

    out_path = Path(out)
    try:
        out_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        print(f"错误：写入失败 {out_path} — {e}", file=sys.stderr)
        sys.exit(1)

    pubkey = private_key.public_key().public_bytes_raw().hex()
    print(
        f"已生成 {out_path}（version={version}，assets={len(assets_map)}）",
        file=sys.stderr,
    )
    print(f"UPDATE_SIGNING_PUBKEY={pubkey}", file=sys.stderr)


if __name__ == "__main__":
    main()
