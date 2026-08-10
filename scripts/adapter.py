"""OTT 适配器包 SDK 命令行工具（ADR-011 Phase 2.5）。

适配器包格式与权威 schema 见 open-typing-texts 仓
（docs/adapter-package.md、schemas/ott-adapter-v1.schema.json），
运行时按兄弟目录相对路径读取。

用法：
    uv run python scripts/adapter.py new demo --type script --repo-id demo.repo
    uv run python scripts/adapter.py validate ./demo
    uv run python scripts/adapter.py sign ./demo --pubkey ed25519:<64hex> --secret-key ed25519:<64hex>
    uv run python scripts/adapter.py debug ./demo --max-pages 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

import jsonschema

# 让脚本能从项目根导入 src 包（与 scripts/debug_rule.py 一致）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "open-typing-texts"
    / "schemas"
    / "ott-adapter-v1.schema.json"
)

# 未签名占位：schema 要求 signature 字段必填；全零值无法通过签名校验，
# validate 步骤识别为"未签名"并给出明确提示。
_UNSIGNED_PUBKEY = "ed25519:" + "0" * 64
_UNSIGNED_SIG = "ed25519:" + "0" * 128

_SCRIPT_STUB = '''"""适配器脚本 stub：实现 fetch_entries() 返回标准化 entry 列表。"""


def fetch_entries() -> list[dict]:
    """返回标准化 entry 列表（content 必填，title/source_key 可选）。"""
    return [
        {
            "title": "示例条目",
            "content": "你好，世界。",
            "source_key": "example",
        }
    ]
'''

_README_TEMPLATE = """# {name}

OTT 适配器包（type={type_}）。

- 来源说明：请补充数据来源与更新频率
- 抓取许可声明：请确认目标站点允许程序化访问

目录结构：
- `adapter.json` — 包清单（含 checksum / signature）
- `code/` — 载荷（script.py / rule.json / endpoints 内联）
- `fixtures/` — 测试数据（mock 响应 / 期望输出）

本地验证：
    uv run python scripts/adapter.py validate .
    uv run python scripts/adapter.py sign . --pubkey ed25519:<64hex> --secret-key ed25519:<64hex>
    uv run python scripts/adapter.py debug . --max-pages 3
"""


# ---------------------------------------------------------------------------
# 哈希 / 签名
# ---------------------------------------------------------------------------


def canonical_bytes(adapter: dict) -> bytes:
    """canonical JSON：剔除 signature、键按字节序排序、无空白、UTF-8。

    与 adapter-package.md §签名与校验 及 ADR-011 决策 12 一致。
    """
    canonical = {k: v for k, v in adapter.items() if k != "signature"}
    return json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _strip_ed25519_prefix(value: str) -> str:
    """去掉 "ed25519:" 前缀；裸 hex 原样返回。"""
    return value.split(":", 1)[1] if ":" in value else value


def verify_ed25519_signature(adapter: dict, pubkey_str: str, sig_str: str) -> bool:
    """验证 ed25519 签名。

    复刻 ott_repo_manifest.RepoManifestCache._verify_ed25519_signature 的
    pubkey/sig 解析逻辑（"ed25519:<hex>" 或裸 hex），签名对象为剔除
    signature 的 canonical JSON。
    """
    try:
        pubkey_bytes = bytes.fromhex(_strip_ed25519_prefix(pubkey_str).strip())
        sig_bytes = bytes.fromhex(_strip_ed25519_prefix(sig_str).strip())
    except ValueError:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        key.verify(sig_bytes, canonical_bytes(adapter))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------


def content_checksum(adapter: dict, package_dir: Path) -> str | None:
    """计算 content 载荷的 sha256；文件缺失/读取失败返回 None。

    type=script/rule → content.path 文件内容；
    type=instance → content 对象（端点声明内联）的 canonical JSON。
    """
    if adapter.get("type") == "instance":
        payload = json.dumps(
            adapter.get("content") or {},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    else:
        path = package_dir / (adapter.get("content") or {}).get("path", "")
        try:
            payload = path.read_bytes()
        except OSError:
            return None
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# new：搭建包目录
# ---------------------------------------------------------------------------


def scaffold(
    package_dir: Path,
    name: str,
    type_: str,
    repo_id: str | None = None,
    api_level: int | None = None,
    network_hosts: list[str] | None = None,
) -> Path:
    """搭建适配器包目录（未签名，占位载荷 + fixtures/ + README.md）。"""
    if type_ not in ("script", "rule", "instance"):
        raise ValueError(f"未知 type: {type_!r}（仅支持 script/rule/instance）")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(f"adapter_id 非法: {name!r}（仅允许 A-Za-z0-9_-）")

    pkg = package_dir / name
    pkg.mkdir(parents=True, exist_ok=True)
    code_dir = pkg / "code"
    code_dir.mkdir(exist_ok=True)
    (pkg / "fixtures" / "responses").mkdir(parents=True, exist_ok=True)

    content: dict[str, Any]
    if type_ == "script":
        content = {"path": "code/script.py"}
        (code_dir / "script.py").write_text(_SCRIPT_STUB, encoding="utf-8")
    elif type_ == "rule":
        content = {"path": "code/rule.json"}
        (code_dir / "rule.json").write_text("{}\n", encoding="utf-8")
    else:  # instance：端点内联，无载荷文件
        content = {"endpoints": [{"url": "https://example.org/"}]}

    adapter: dict[str, Any] = {
        "protocol": "ott-adapter",
        "version": 1,
        "adapter_id": name,
        "name": name,
        "repo_id": repo_id or "local",
        "type": type_,
        "content": content,
        "fixtures": "fixtures",
        "signature": {"pubkey": _UNSIGNED_PUBKEY, "sig": _UNSIGNED_SIG},
    }
    if api_level is not None:
        adapter["rights"] = {"min_api_level": api_level}
    if network_hosts:
        adapter["permissions"] = {"network": network_hosts}
    adapter["checksum"] = content_checksum(adapter, pkg)

    try:
        jsonschema.validate(adapter, _load_schema())
    except jsonschema.ValidationError as e:
        print(
            f"警告：scaffold 产物未通过 schema 校验（仍写入）: {e.message}",
            file=sys.stderr,
        )

    (pkg / "adapter.json").write_text(
        json.dumps(adapter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (pkg / "README.md").write_text(
        _README_TEMPLATE.format(name=name, type_=type_), encoding="utf-8"
    )
    return pkg


def _load_schema() -> dict:
    """运行时读取权威 schema（路径相对本脚本，避免复制两份定义）。"""
    if not SCHEMA_PATH.exists():
        raise SystemExit(f"未找到 open-typing-texts 兄弟仓 schema: {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# validate：完整校验链
# ---------------------------------------------------------------------------


def validate_package(package_dir: Path) -> list[tuple[str, bool, str]]:
    """完整校验链：(1) schema (2) checksum (3) 签名 (4) 权限 (5) rights (6) rule 解析。

    返回 [(步骤名, 是否通过, 消息)]，不抛异常；CLI 层汇总决定退出码。
    """
    steps: list[tuple[str, bool, str]] = []
    adapter_path = package_dir / "adapter.json"
    if not adapter_path.exists():
        return [("读取", False, f"adapter.json 不存在: {adapter_path}")]
    try:
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [("读取", False, f"adapter.json 解析失败: {e}")]

    # (1) schema
    try:
        jsonschema.validate(adapter, _load_schema())
        steps.append(("schema", True, "符合 ott-adapter-v1 schema"))
    except jsonschema.ValidationError as e:
        steps.append(("schema", False, f"schema 校验失败: {e.message}"))

    # (2) checksum：content 载荷未变
    expected = adapter.get("checksum", "")
    actual = content_checksum(adapter, package_dir)
    if actual is None:
        steps.append(
            (
                "checksum",
                False,
                f"content 载荷文件缺失: {(adapter.get('content') or {}).get('path', '')}",
            )
        )
    elif actual == expected:
        steps.append(("checksum", True, f"匹配 ({actual})"))
    else:
        steps.append(("checksum", False, f"不匹配: 期望 {expected}, 实际 {actual}"))

    # (3) 签名：canonical JSON 剔除 signature 后 ed25519 验证
    sig = adapter.get("signature") or {}
    pubkey_str = sig.get("pubkey", "")
    sig_str = sig.get("sig", "")
    if not pubkey_str or not sig_str:
        steps.append(("signature", False, "缺少 signature.pubkey/sig（未签名）"))
    elif pubkey_str == _UNSIGNED_PUBKEY and sig_str == _UNSIGNED_SIG:
        steps.append(("signature", False, "未签名（占位签名，先运行 sign 子命令）"))
    elif verify_ed25519_signature(adapter, pubkey_str, sig_str):
        steps.append(("signature", True, "ed25519 签名校验通过"))
    else:
        steps.append(
            ("signature", False, "ed25519 签名校验失败（载荷被篡改或签名无效）")
        )

    # (4) permissions 白名单 sanity
    perms = adapter.get("permissions") or {}
    if "storage" in perms or "process" in perms:
        steps.append(
            (
                "permissions",
                False,
                "permissions 不允许 storage/process 字段（默认 none）",
            )
        )
    else:
        hosts = perms.get("network") or []
        bad = [h for h in hosts if not h or "://" in h]
        if bad:
            steps.append(("permissions", False, f"非法网络白名单主机: {bad}"))
        else:
            steps.append(
                (
                    "permissions",
                    True,
                    f"network 白名单 {len(hosts)} 个主机，无 storage/process",
                )
            )

    # (5) rights.min_api_level 对照 CLIENT_API_LEVEL
    from src.backend.integration.ott_rule_interpreter import CLIENT_API_LEVEL

    rights = adapter.get("rights") or {}
    min_level = rights.get("min_api_level", 1)
    if not isinstance(min_level, int) or min_level > CLIENT_API_LEVEL:
        steps.append(
            (
                "rights",
                False,
                f"min_api_level={min_level} > CLIENT_API_LEVEL={CLIENT_API_LEVEL}（客户端不支持）",
            )
        )
    else:
        steps.append(
            (
                "rights",
                True,
                f"min_api_level={min_level} ≤ CLIENT_API_LEVEL={CLIENT_API_LEVEL}",
            )
        )

    # (6) type=rule：载荷为可解析的 rule dict（mock 执行仅在 debug）
    if adapter.get("type") == "rule":
        rule_path = package_dir / (adapter.get("content") or {}).get("path", "")
        try:
            rule = json.loads(rule_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            steps.append(("rule", False, f"rule 载荷解析失败: {e}"))
        else:
            if isinstance(rule, dict):
                steps.append(
                    ("rule", True, f"rule 字典解析通过（{len(rule)} 个顶层键）")
                )
            else:
                steps.append(("rule", False, "rule 载荷不是 JSON 对象"))
    else:
        steps.append(("rule", True, "type≠rule，跳过"))

    return steps


# ---------------------------------------------------------------------------
# sign：写入 ed25519 签名
# ---------------------------------------------------------------------------


def sign_package(package_dir: Path, pubkey_hex: str, secret_key_hex: str) -> Path:
    """对 adapter.json 写入 ed25519 签名并落盘。

    签名对象为剔除 signature 的 canonical JSON；pubkey/secret_key 支持
    "ed25519:<hex>" 或裸 hex，secret_key 兼容 32/64 字节。
    """
    adapter_path = package_dir / "adapter.json"
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))

    priv_bytes = bytes.fromhex(_strip_ed25519_prefix(secret_key_hex).strip())
    if len(priv_bytes) == 64:  # seed+pubkey 拼合形式，取前 32 字节 seed
        priv_bytes = priv_bytes[:32]
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    sig = priv.sign(canonical_bytes(adapter))
    adapter["signature"] = {
        "pubkey": "ed25519:" + _strip_ed25519_prefix(pubkey_hex).strip(),
        "sig": "ed25519:" + sig.hex(),
    }
    adapter_path.write_text(
        json.dumps(adapter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return adapter_path


# ---------------------------------------------------------------------------
# debug：执行载荷并打印条目
# ---------------------------------------------------------------------------


def _print_entries(entries: list[dict]) -> None:
    if not entries:
        print("未抓到任何条目。")
        return
    print(f"抓到 {len(entries)} 条：\n")
    for i, entry in enumerate(entries, 1):
        content_preview = (entry.get("content") or "")[:80].replace("\n", " ")
        print(f"[{i}] entry_id={entry.get('entry_id', '')}")
        print(f"    title={entry.get('title', '')!r}")
        print(f"    char_count={entry.get('char_count', 0)}")
        print(f"    authority={entry.get('authority', '')}")
        print(f"    content={content_preview!r}")
        print()


def run_debug(package_dir: Path, max_pages: int) -> int:
    """执行载荷（rule 走 OttRuleInterpreter；script 走 ScriptSandbox）并打印条目。

    script 类型若存在 fixtures/ 目录，通过 OTT_FIXTURES_DIR 环境变量传给
    沙箱子进程（runner 侧可读取做 mock 响应注入）。
    """
    try:
        adapter = json.loads((package_dir / "adapter.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"错误：adapter.json 解析失败: {e}", file=sys.stderr)
        return 1

    type_ = adapter.get("type")
    content = adapter.get("content") or {}
    fixtures_dir = package_dir / (adapter.get("fixtures") or "fixtures")

    if type_ == "rule":
        rule_path = package_dir / content.get("path", "code/rule.json")
        try:
            rule = json.loads(rule_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"错误：rule 载荷解析失败: {e}", file=sys.stderr)
            return 1

        import httpx

        from src.backend.integration.ott_rule_interpreter import (
            CLIENT_API_LEVEL,
            OttRuleInterpreter,
        )

        print(f"rule_id: {adapter['adapter_id']}")
        print(f"request: {rule.get('request', {})}")
        print(f"extract: {rule.get('extract', {})}")
        print(f"transform: {rule.get('transform', [])}")
        print(f"pagination: {rule.get('pagination', {})}")
        print("-" * 60)

        with httpx.Client(timeout=10.0, trust_env=False) as client:
            interpreter = OttRuleInterpreter(client, api_level=CLIENT_API_LEVEL)
            entries = interpreter.list_entries(
                rule, adapter["adapter_id"], max_pages=max_pages
            )
        _print_entries(entries)
        return 0

    if type_ == "script":
        source = (package_dir / content.get("path", "code/script.py")).read_text(
            encoding="utf-8"
        )

        from src.backend.integration.ott_script_client import ScriptSandbox

        if fixtures_dir.is_dir():
            os.environ["OTT_FIXTURES_DIR"] = str(fixtures_dir)
            print(f"fixtures 目录: {fixtures_dir}")
        print(f"script: {content.get('path', 'code/script.py')}")
        print("-" * 60)
        sandbox = ScriptSandbox()
        entries = sandbox.execute(
            source, f"file://{adapter['adapter_id']}/code/script.py"
        )
        _print_entries(entries)
        return 0

    if type_ == "instance":
        print("instance 端点（无执行）:")
        print(json.dumps(content.get("endpoints", []), ensure_ascii=False, indent=2))
        return 0

    print(f"错误：未知 type {type_!r}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OTT 适配器包 SDK 工具（new / validate / sign / debug）"
    )
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    sub = parser.add_subparsers(dest="command", required=True, help="子命令")

    p_new = sub.add_parser("new", help="搭建适配器包目录")
    p_new.add_argument("name", help="adapter_id（仅允许 A-Za-z0-9_-）")
    p_new.add_argument(
        "--type",
        required=True,
        choices=["script", "rule", "instance"],
        help="适配器类型",
    )
    p_new.add_argument("--repo-id", default=None, help="归属仓库（默认 local）")
    p_new.add_argument(
        "--api-level", type=int, default=None, help="rights.min_api_level"
    )
    p_new.add_argument(
        "--network-host",
        default=None,
        help="permissions.network 域名白名单（逗号分隔）",
    )
    p_new.set_defaults(func=cmd_new)

    p_val = sub.add_parser(
        "validate", help="校验适配器包（schema/checksum/签名/权限/rights/rule）"
    )
    p_val.add_argument("package_dir", help="包目录")
    p_val.set_defaults(func=cmd_validate)

    p_sign = sub.add_parser("sign", help="写入 ed25519 签名")
    p_sign.add_argument("package_dir", help="包目录")
    p_sign.add_argument("--pubkey", required=True, help="ed25519:<64hex> 或裸 64hex")
    p_sign.add_argument(
        "--secret-key", required=True, help="ed25519:<64hex> 或裸 64hex（32/64 字节）"
    )
    p_sign.set_defaults(func=cmd_sign)

    p_debug = sub.add_parser("debug", help="执行载荷并打印条目")
    p_debug.add_argument("package_dir", help="包目录")
    p_debug.add_argument(
        "--max-pages", type=int, default=5, help="规则最大分页数（默认 5）"
    )
    p_debug.set_defaults(func=cmd_debug)

    return parser


def cmd_new(args: argparse.Namespace) -> int:
    hosts = (
        [h.strip() for h in args.network_host.split(",") if h.strip()]
        if args.network_host
        else None
    )
    try:
        pkg = scaffold(
            Path.cwd(),
            args.name,
            args.type,
            repo_id=args.repo_id,
            api_level=args.api_level,
            network_hosts=hosts,
        )
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    print(f"已搭建适配器包: {pkg}")
    if args.verbose:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                print(f"  - {f.relative_to(pkg)}")
    print(f"下一步：uv run python scripts/adapter.py validate {pkg}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    steps = validate_package(Path(args.package_dir))
    failed = False
    for i, (name, ok, msg) in enumerate(steps, 1):
        mark = "通过" if ok else "失败"
        print(f"[{mark}] {i}.{name}: {msg}")
        if not ok:
            failed = True
    if failed:
        print("校验失败：至少一项未通过", file=sys.stderr)
        return 1
    print("校验全部通过")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    try:
        sign_package(Path(args.package_dir), args.pubkey, args.secret_key)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"错误：签名失败: {e}", file=sys.stderr)
        return 1
    print("签名已写入 adapter.json")
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    return run_debug(Path(args.package_dir), args.max_pages)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
