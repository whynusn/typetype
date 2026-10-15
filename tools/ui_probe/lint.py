"""QML 静态规则：补 qmllint 抓不到的那一类缺陷（ADR-015 背景 2）。

`qmllint` 只做类型解析，抓不到**语义正确但作用域错**的写法。已实测的两类：

1. RinaUI 模块外的未解析类型（`ItemDelegate is not a type`）——由运行时冒烟兜住。
2. **在 ``Connections`` 的信号处理器里引用 ``Window.window``**：Connections
   不是 Item，附加属性无从解析，Qt 会在**每次信号分发**时报一次警告。
   静态看完全合法，只有真机跑一轮交互才显形（实测一轮打字刷 900+ 条）。

本模块做第 2 类的静态拦截——便宜、确定、能在提交前就拦下。
"""

from __future__ import annotations

import re
from pathlib import Path

# 块头：`Connections {` / `QQC.Connections {` / `Rin.Connections {`
_BLOCK_HEAD = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*\{")
# 块头：`Connections {` 后接属性（`Connections { target: x }`）
_IDENTIFIER = re.compile(r"[\w.]+")

# 只有 Item 派生的类型才能解析 Window.* 附加属性
_ITEM_ONLY_ATTACHED = ("Window.window", "Window.active", "Window.visibility")

# 这些类型不是 Item，其内部作用域取不到 Window 附加属性
_NON_ITEM_SCOPES = ("Connections",)


def _strip_comment(line: str) -> str:
    """去掉行注释（QML 无多行注释参与的块结构，够用）。"""
    index = line.find("//")
    return line[:index] if index >= 0 else line


def scan_window_attached_in_connections(path: Path) -> list[dict]:
    """返回 Connections 块内引用 Item 附加属性的位置。"""
    text = Path(path).read_text(encoding="utf-8")
    findings: list[dict] = []
    stack: list[str] = []  # 块类型名（按花括号深度）

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        head = _BLOCK_HEAD.match(line)
        # 逐字符维护作用域栈：同一行可能开多个块（内联处理器）
        for char in line:
            if char == "{":
                stack.append(head.group(1) if head else "")
                head = None  # 行首块头只作用于本行第一个块
            elif char == "}" and stack:
                stack.pop()

        # 栈状态取本行**处理之后**：这样 `Connections { onX: ...Window.window }`
        # 这种单行写法也能被抓到
        in_non_item_scope = any(
            scope.rsplit(".", 1)[-1] in _NON_ITEM_SCOPES for scope in stack
        )
        if not in_non_item_scope:
            continue
        for attached in _ITEM_ONLY_ATTACHED:
            if attached in line:
                findings.append(
                    {
                        "file": str(path),
                        "line": lineno,
                        "rule": "window-attached-in-connections",
                        "attached": attached,
                        "message": (
                            f"Connections 内引用 {attached}：Connections 不是 Item，"
                            f"附加属性无从解析，运行时每次信号分发都会报一次警告"
                        ),
                        "snippet": raw.strip()[:120],
                    }
                )

    return findings


def scan_tree(root: Path) -> list[dict]:
    """扫描仓库内全部 QML。"""
    findings: list[dict] = []
    for path in sorted(Path(root).glob("src/**/*.qml")):
        findings.extend(scan_window_attached_in_connections(path))
    return findings
