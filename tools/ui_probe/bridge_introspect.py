"""从 bridge.py 解析 QML 可见的 API 面（Property / Slot / Signal）。

用 ast 解析而非正则：签名可跨行、注解结构化，且天然免疫行尾注释——
早期正则方案（``\\w+\\s*=\\s*Signal\\(.*\\)$``）会被
``textLoaded = Signal(str)  # 注释`` 整行漏抓，导致 mock bridge 缺信号、
QML ``Connections`` 报 "no signal of the target matches"。

产出：
- properties: name -> QML 类型。``list``/``QVariantList`` 归一为伪类型
  ``"list"``（真实语义是 var，但默认值应为 ``[]`` 而非 ``null``）。
- slots: name -> Python 返回注解（供 mock bridge 生成类型化返回值；
  空实现返回 undefined，赋给 QString 属性会触发
  "Cannot assign [undefined] to QString"）。
- signals: name -> 参数个数。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


# bridge.py 的 Property 类型参数 -> QML 属性类型
_QML_TYPE_MAP = {
    "bool": "bool",
    "str": "string",
    "int": "int",
    "float": "real",
    "list": "list",
    "QVariantList": "list",
    "dict": "var",
    "QVariantMap": "var",
    "QVariant": "var",
    "object": "var",
    "QObject": "var",
}


@dataclass
class BridgeApi:
    """bridge.py 暴露给 QML 的 API 面。"""

    properties: dict[str, str] = field(default_factory=dict)  # name -> qml 类型
    slots: dict[str, str] = field(default_factory=dict)  # name -> 返回注解
    signals: dict[str, int] = field(default_factory=dict)  # name -> 参数个数


def _decorator_name(node: ast.expr) -> str:
    """取装饰器/被调用者的名称（兼容 Name 与 Attribute）。"""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _annotation_name(node: ast.expr | None) -> str:
    """取注解的类型名；Subscript（如 list[str]）取基名。"""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        return _annotation_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _property_qml_type(decorator: ast.expr) -> str:
    """``@Property("QVariantList", ...)`` -> QML 属性类型。"""
    args = decorator.args if isinstance(decorator, ast.Call) else []
    if args:
        return _QML_TYPE_MAP.get(_annotation_name(args[0]), "var")
    return "var"


def parse_bridge_api(source: str) -> BridgeApi:
    """解析 bridge.py 源码，返回 QML 可见 API 面。"""
    api = BridgeApi()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in item.decorator_list:
                    name = _decorator_name(decorator)
                    if name == "Property":
                        api.properties[item.name] = _property_qml_type(decorator)
                    elif name == "Slot":
                        api.slots[item.name] = _annotation_name(item.returns)
            elif isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                if _decorator_name(item.value.func) != "Signal":
                    continue
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        api.signals[target.id] = len(item.value.args)

    return api


def parse_bridge_file(path) -> BridgeApi:
    """从 bridge.py 文件路径解析。"""
    with open(path, encoding="utf-8") as handle:
        return parse_bridge_api(handle.read())
