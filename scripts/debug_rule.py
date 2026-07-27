"""OTT Repo L1 声明式规则调试工具。

用法：
    uv run python scripts/debug_rule.py --rule-file rule.json [--max-pages 3]
    uv run python scripts/debug_rule.py --rule-json '{"request":{...}, "extract":{...}}'

功能：
    1. 从文件或 CLI 参数加载 rule JSON
    2. 实例化 OttRuleInterpreter
    3. 执行 list_entries
    4. 打印每条 entry 的 entry_id / title / char_count / content 前 80 字
    5. 打印错误（URL 校验失败、提取失败、网络错误）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

# 让脚本能从项目根导入 src 包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_rule(args: argparse.Namespace) -> tuple[dict, str]:
    """从 --rule-file 或 --rule-json 加载规则。"""
    if args.rule_file:
        path = Path(args.rule_file)
        if not path.exists():
            print(f"错误：文件不存在 {path}", file=sys.stderr)
            sys.exit(1)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        # 支持两种格式：直接 rule 对象，或包含 rule + rule_id 的 source 对象
        if "rule" in data and isinstance(data["rule"], dict):
            rule = data["rule"]
            rule_id = data.get("rule_id", path.stem)
        else:
            rule = data
            rule_id = path.stem
        return rule, rule_id

    if args.rule_json:
        data = json.loads(args.rule_json)
        if "rule" in data and isinstance(data["rule"], dict):
            return data["rule"], data.get("rule_id", "cli-rule")
        return data, "cli-rule"

    print("错误：必须指定 --rule-file 或 --rule-json", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="OTT Repo L1 规则调试工具")
    parser.add_argument("--rule-file", help="rule JSON 文件路径")
    parser.add_argument("--rule-json", help="rule JSON 字符串")
    parser.add_argument("--max-pages", type=int, default=3, help="最大分页数（默认 3）")
    parser.add_argument("--max-bytes", type=int, default=1_048_576, help="单页最大字节（默认 1MB）")
    args = parser.parse_args()

    rule, rule_id = load_rule(args)

    print(f"rule_id: {rule_id}")
    print(f"request: {rule.get('request', {})}")
    print(f"extract: {rule.get('extract', {})}")
    print(f"transform: {rule.get('transform', [])}")
    print(f"pagination: {rule.get('pagination', {})}")
    print("-" * 60)

    from src.backend.integration.ott_rule_interpreter import OttRuleInterpreter

    with httpx.Client(timeout=10.0, trust_env=False) as client:
        interpreter = OttRuleInterpreter(client, max_bytes=args.max_bytes)
        entries = interpreter.list_entries(rule, rule_id, max_pages=args.max_pages)

    if not entries:
        print("未抓到任何条目。可能原因：")
        print("  - URL 校验失败（file:/环回/私有地址被拒绝）")
        print("  - 网络请求失败")
        print("  - extract 规则未匹配到任何字段")
        print(f"  - 首条请求 URL: {rule.get('request', {}).get('url', 'N/A')}")
        sys.exit(0)

    print(f"抓到 {len(entries)} 条：\n")
    for i, entry in enumerate(entries, 1):
        content_preview = (entry.get("content") or "")[:80].replace("\n", " ")
        print(f"[{i}] entry_id={entry.get('entry_id', '')}")
        print(f"    title={entry.get('title', '')!r}")
        print(f"    char_count={entry.get('char_count', 0)}")
        print(f"    authority={entry.get('authority', '')}")
        print(f"    content={content_preview!r}")
        print()


if __name__ == "__main__":
    main()
