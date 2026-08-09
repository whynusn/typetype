"""OTT Repo L1 正则子进程执行器。

正则匹配从宿主进程移出，防止恶意规则 (a+)+ 类灾难性回溯拖死主进程。
调用方负责 1s 硬超时（subprocess.run timeout）；本 worker 只依赖 stdlib，
保证子进程启动开销最小。

协议（stdin → stdout，均为 JSON）：
- 输入: {"pattern": str, "text": str}
- 输出: {"ok": true, "groups": {name: value}} 或 {"ok": true, "content": str}
        或 {"ok": false, "error": str}
"""

from __future__ import annotations

import json
import re
import signal
import sys
from typing import Any

# 输入大小上限（调用方从本模块导入，单点定义防漂移）
REGEX_WORKER_MAX_INPUT_CHARS = 10_000


def _safe_alternation(branches: list[str]) -> bool:
    """交替分支是否无歧义：全为互不相同的单字符字面量。

    (a|b)+ 安全（每个分支匹配不同单字符）；(a|a)+ / (a|aa)+ / (a|ab)+
    均可能歧义回溯，拒绝。
    """
    seen: set[str] = set()
    for branch in branches:
        if len(branch) != 1 or branch in seen or branch in "()+*?{|[]^$.":
            return False
        seen.add(branch)
    return True


def _has_nested_quantifier(pattern: str) -> bool:
    """静态拒绝灾难性回溯模式：(a+)+ 类量词嵌套、(a|a)+ 类歧义交替。

    栈跟踪每层括号组：组内是否已出现量词、交替分支列表。
    组后紧跟量词时，若组内含量词或交替有歧义 → 拒绝。
    """
    stack: list[dict[str, Any]] = []
    in_class = False
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            in_class = True
            i += 1
            continue
        if ch == "]":
            in_class = False
            i += 1
            continue
        if in_class:
            i += 1
            continue
        if ch == "(":
            stack.append({"has_quant": False, "branches": [], "cur_branch": ""})
            i += 1
            continue
        if ch == "|":
            if stack:
                stack[-1]["branches"].append(stack[-1]["cur_branch"])
                stack[-1]["cur_branch"] = ""
            i += 1
            continue
        if ch == ")":
            if not stack:
                i += 1
                continue
            group = stack.pop()
            group["branches"].append(group["cur_branch"])
            quant_after = i + 1 < n and pattern[i + 1] in "+*{"
            if group["has_quant"] and quant_after:
                return True
            if quant_after and len(group["branches"]) > 1:
                if not _safe_alternation(group["branches"]):
                    return True
            if stack:
                if quant_after:
                    stack[-1]["has_quant"] = True
                if group["has_quant"]:
                    stack[-1]["has_quant"] = True
            i += 1
            continue
        if ch in "+*{":
            if stack:
                stack[-1]["has_quant"] = True
        elif stack:
            stack[-1]["cur_branch"] += ch
        i += 1
    return False


def _timeout_handler(signum: int, frame: Any) -> None:
    """SIGALRM 处理器：正则执行超时（1s）抛 TimeoutError。"""
    raise TimeoutError("regex execution timeout")


def _run(pattern: str, text: str, op: str = "search", repl: str = "") -> dict:
    if (
        len(pattern) > REGEX_WORKER_MAX_INPUT_CHARS
        or len(text) > REGEX_WORKER_MAX_INPUT_CHARS
    ):
        return {"ok": False, "error": "input_too_large"}
    if _has_nested_quantifier(pattern):
        return {"ok": False, "error": "nested_quantifier"}
    try:
        # 第二道防线：POSIX 下用 SIGALRM 自限 1s（Windows 无 alarm，跳过）。
        # 只包正则执行，import/输入读取不计时；结束复位 alarm(0)。
        if hasattr(signal, "alarm"):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(1)
        try:
            if op == "replace":
                return {
                    "ok": True,
                    "content": re.sub(pattern, repl, text, flags=re.DOTALL),
                }
            match = re.search(pattern, text, re.DOTALL)
        finally:
            if hasattr(signal, "alarm"):
                signal.alarm(0)
    except re.error:
        return {"ok": False, "error": "regex_error"}
    except TimeoutError:
        return {"ok": False, "error": "timeout"}
    if match is None:
        return {"ok": True, "groups": {}}
    groups = match.groupdict()
    if groups:
        return {
            "ok": True,
            "groups": {k: (v if v is not None else "") for k, v in groups.items()},
        }
    try:
        return {"ok": True, "content": match.group(1)}
    except IndexError:
        return {"ok": True, "groups": {}}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        pattern = payload.get("pattern", "")
        text = payload.get("text", "")
        op = payload.get("op", "search")
        repl = payload.get("repl", "")
        if not isinstance(pattern, str) or not isinstance(text, str):
            print(json.dumps({"ok": False, "error": "bad_input"}))
            return 0
        if op not in ("search", "replace") or not isinstance(repl, str):
            print(json.dumps({"ok": False, "error": "bad_input"}))
            return 0
        result = _run(pattern, text, op, repl)
    except (json.JSONDecodeError, ValueError, OSError):
        result = {"ok": False, "error": "bad_input"}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
