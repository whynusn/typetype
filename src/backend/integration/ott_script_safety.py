"""OTT Repo ott-script AST 安全检查。

在 exec 之前对脚本源码做静态分析，拦截明显恶意代码。
复用 open-typing-texts ott_adapter/script_safety.py 的检查逻辑，
独立实现以避免跨仓依赖。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TypeAlias

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonMap: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> JsonMap:
        return {
            "valid": self.valid,
            "issues": [
                {"code": issue.code, "path": issue.path, "message": issue.message}
                for issue in self.issues
            ],
        }


# ── 黑名单 ──────────────────────────────────────────────────────────────

# 危险模块（禁止 import）
BANNED_IMPORTS = frozenset(
    {
        "ctypes",
        "pty",
        "socket",
        "subprocess",
        "multiprocessing",
    }
)

# 危险内置函数
BANNED_BUILTIN_CALLS = frozenset({"eval", "exec", "compile", "__import__"})

# 危险属性调用：(模块, 函数名)
BANNED_ATTRIBUTE_CALLS = frozenset(
    {
        ("os", "system"),
        ("os", "popen"),
        ("os", "execv"),
        ("os", "execl"),
        ("os", "spawn"),
    }
)

# 危险 from-import
BANNED_FROM_IMPORTS = frozenset(
    {
        ("os", "system"),
        ("os", "popen"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("subprocess", "run"),
    }
)

# 对象模型逃逸危险属性（禁止属性访问）
#
# 逃逸链：().__class__.__bases__[0].__subclasses__() 枚举 object 的全部子类
# → c.__init__.__globals__ 拿到模块 globals（含 open/subprocess/socket 等未
# 白名单能力）。这些步骤全是属性访问而非函数调用，可绕过 BANNED_BUILTIN_CALLS
# 与运行时受限 builtins，故在此按属性名拦截（AST 层第一道防线）。
#
# 只拦「属性访问」，不拦「方法定义」：
# - `def __init__(self)` 是 ast.FunctionDef 的 name，不是 ast.Attribute，不受影响；
# - `super().__init__()` 是合法类模式，依赖 __init__ 属性访问，故 __init__ 不列入
#   （逃逸链下一步 __globals__/__closure__/__code__/__dict__ 已被拦截）；
# - 白名单库（httpx/bs4/Crypto/json/re/datetime）的用户级调用不涉及这些属性。
BANNED_DUNDER_ATTRIBUTES = frozenset(
    {
        "__class__",
        "__mro__",
        "__bases__",
        "__subclasses__",
        "__globals__",
        "__closure__",
        "__code__",
        "__dict__",
        "__builtins__",
        "__self__",
        "__func__",
        "__getattribute__",
        "__getattr__",
        "__setattr__",
        "__delattr__",
        "__module__",
    }
)

# 允许白名单（import 仅允许这些模块）
ALLOWED_MODULES = frozenset(
    {
        "json",
        "re",
        "time",
        "datetime",
        "hashlib",
        "base64",
        "urllib.parse",
        "http",
        "email",
        "collections",
        "itertools",
        "functools",
        "math",
        "random",
        "string",
        "textwrap",
        "unicodedata",
        "httpx",
        "Crypto",  # pycryptodome
        "Crypto.Cipher",
        "Crypto.Util",
        "Crypto.Util.Padding",
        "bs4",
        "BeautifulSoup",
    }
)


# ── 公开 API ────────────────────────────────────────────────────────────


def validate_script_source(
    source: str, display_path: str = "<source>"
) -> ValidationReport:
    """对脚本源码做 AST 安全检查。"""
    try:
        tree = ast.parse(source, filename=display_path)
    except SyntaxError as error:
        return ValidationReport(
            (ValidationIssue("invalid_python", display_path, str(error)),)
        )

    issues: list[ValidationIssue] = []
    assignments = _collect_assignments(tree)
    import_aliases = _collect_import_aliases(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                issues.extend(_validate_import(alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            issues.extend(_validate_import(node.module or "", node.lineno))
            issues.extend(_validate_from_import(node))
        elif isinstance(node, ast.Call):
            target = _resolve_call_target(node.func, import_aliases, assignments)
            issue = _validate_call(node, target)
            if issue is not None:
                issues.append(issue)
            dynamic_issue = _validate_dynamic_import(node, target)
            if dynamic_issue is not None:
                issues.append(dynamic_issue)
        elif isinstance(node, ast.Constant) and node.value == "__builtins__":
            # 检测 __builtins__ 字面量（常用于沙箱逃逸）
            issues.append(
                ValidationIssue(
                    "banned_builtins_ref",
                    f"line {getattr(node, 'lineno', '?')}",
                    "script references __builtins__",
                )
            )
        elif isinstance(node, ast.Name) and node.id == "__builtins__":
            issues.append(
                ValidationIssue(
                    "banned_builtins_ref",
                    f"line {node.lineno}",
                    "script references __builtins__",
                )
            )
        elif isinstance(node, ast.Attribute):
            issue = _validate_attribute_access(node)
            if issue is not None:
                issues.append(issue)

    return ValidationReport(tuple(issues))


# ── 内部实现 ────────────────────────────────────────────────────────────


def _validate_import(module: str, lineno: int) -> list[ValidationIssue]:
    """白名单逻辑：仅允许 ALLOWED_MODULES 中的模块或其子模块。"""
    if any(
        module == allowed or module.startswith(allowed + ".")
        for allowed in ALLOWED_MODULES
    ):
        return []
    return [
        ValidationIssue(
            "banned_import",
            f"line {lineno}",
            f"script imports non-whitelisted module {module}",
        )
    ]


def _validate_attribute_access(node: ast.Attribute) -> ValidationIssue | None:
    if node.attr in BANNED_DUNDER_ATTRIBUTES:
        return ValidationIssue(
            "banned_object_model_access",
            f"line {node.lineno}",
            f"script accesses banned object-model attribute {node.attr}",
        )
    return None


def _validate_from_import(node: ast.ImportFrom) -> list[ValidationIssue]:
    module = node.module or ""
    issues: list[ValidationIssue] = []
    for alias in node.names:
        if (module, alias.name) in BANNED_FROM_IMPORTS:
            issues.append(
                ValidationIssue(
                    "banned_import",
                    f"line {node.lineno}",
                    f"script imports high-risk function {module}.{alias.name}",
                )
            )
    return issues


def _validate_call(node: ast.Call, target: _CallTarget) -> ValidationIssue | None:
    if target.module == "builtins" and target.attr in BANNED_BUILTIN_CALLS:
        return ValidationIssue(
            "banned_call",
            f"line {node.lineno}",
            f"script calls high-risk function {target.attr}",
        )
    if (target.module, target.attr) in BANNED_ATTRIBUTE_CALLS:
        return ValidationIssue(
            "banned_call",
            f"line {node.lineno}",
            f"script calls high-risk function {target.module}.{target.attr}",
        )
    return None


def _validate_dynamic_import(
    node: ast.Call, target: _CallTarget
) -> ValidationIssue | None:
    if not node.args:
        return None
    if not (
        (target.module, target.attr) == ("importlib", "import_module")
        or (target.module, target.attr) == ("builtins", "__import__")
    ):
        return None
    module = _literal_str(node.args[0])
    if module is None:
        return ValidationIssue(
            "banned_dynamic_import",
            f"line {node.lineno}",
            "script dynamically imports a non-literal module",
        )
    root = module.split(".", maxsplit=1)[0]
    if root in ALLOWED_MODULES:
        return None
    return ValidationIssue(
        "banned_dynamic_import",
        f"line {node.lineno}",
        f"script dynamically imports high-risk module {root}",
    )


def _collect_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            assignments[node.target.id] = node.value
    return assignments


def _collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    """收集 import 别名：{本地名: 完整模块路径}。"""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                aliases[name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname if alias.asname else alias.name
                aliases[local] = f"{module}.{alias.name}" if module else alias.name
    return aliases


@dataclass(frozen=True, slots=True)
class _CallTarget:
    module: str
    attr: str


def _resolve_call_target(
    func: ast.AST,
    import_aliases: dict[str, str],
    assignments: dict[str, ast.AST],
) -> _CallTarget:
    """解析调用目标为 (module, attr)。

    使用 import_aliases 和 assignments 解析别名，检测 e=eval; e(...) 类绕过。
    """
    if isinstance(func, ast.Name):
        name = func.id
        # 先查 import 别名
        if name in import_aliases:
            full = import_aliases[name]
            parts = full.rsplit(".", 1)
            return _CallTarget(parts[0], parts[1] if len(parts) > 1 else name)
        # 再查赋值别名（e = eval → e(...) 视为 builtins.eval）
        if name in assignments:
            assigned = assignments[name]
            if isinstance(assigned, ast.Name) and assigned.id in BANNED_BUILTIN_CALLS:
                return _CallTarget("builtins", assigned.id)
        return _CallTarget("builtins", name)
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            base = func.value.id
            if base in import_aliases:
                return _CallTarget(import_aliases[base], func.attr)
            return _CallTarget(base, func.attr)
        if isinstance(func.value, ast.Attribute):
            if isinstance(func.value.value, ast.Name):
                base = func.value.value.id
                if base in import_aliases:
                    return _CallTarget(import_aliases[base], func.attr)
                return _CallTarget(base, func.attr)
    return _CallTarget("", "")


def _literal_str(node: ast.AST) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )
