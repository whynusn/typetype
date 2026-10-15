"""语义选择器：在活动对象树里定位节点（ADR-015 决策 6）。

场景 DSL 只允许用**语义**指认节点——role / text / objectName / path /
属性过滤，**不得 import 任何 typetype 或 RinUI 类型**。这样场景文件与
具体 UI 库解耦，换一套组件库场景仍能读、能评审、能 diff。

``role`` 是从节点自身形态**推断**的伪 a11y 角色（本项目 objectName
绝大多数为空，只能靠形态 + 文本）：

- ``text-input``  可编辑文本（有 text 且 readOnly=false）
- ``static-text`` 只读文本（有 text 且 readOnly=true，或纯展示 Text）
- ``button``      类型名以 Button 结尾（RinUI/QtQuick.Controls 通吃）
- ``checkbox``    有 checked（Switch / CheckBox / RadioButton）
- ``list``        有 count / rows（ListView / TableView / Repeater 宿主）
- ``generic``     其余

多命中用 ``index`` 取第 n 个（默认 0）；``path`` 是精确索引路径
（``0/2/1``），形状变化时比文本更稳。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem

from .snapshot import normalize_type

# 承担"文本标识"职责的属性（与快照一致，两处口径必须同步）
_TEXT_PROPS = ("text", "title", "label", "description", "placeholderText")


@dataclass
class Selector:
    """声明式选择器（YAML 直接反序列化）。"""

    role: str | None = None
    text: str | None = None  # 包含匹配
    text_equals: str | None = None  # 全等匹配
    objectName: str | None = None
    type: str | None = None  # 归一化类型名，包含匹配（兜底手段）
    path: str | None = None  # 精确索引路径，如 "0/2/1"
    props: dict = field(default_factory=dict)  # 属性等值过滤（readOnly/visible…）
    context: str | None = None  # 取 QML 上下文对象（如 appBridge），非可视化节点
    index: int = 0  # 多命中取第 n 个

    @classmethod
    def from_dict(cls, data: dict | None) -> Selector:
        data = dict(data or {})
        known = {
            "role",
            "text",
            "text_equals",
            "objectName",
            "type",
            "path",
            "props",
            "context",
            "index",
        }
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"选择器含未知字段 {sorted(unknown)}（可用：{sorted(known)}）"
            )
        return cls(**data)

    def describe(self) -> str:
        parts = []
        for key in (
            "context",
            "role",
            "type",
            "objectName",
            "text",
            "text_equals",
            "path",
        ):
            value = getattr(self, key)
            if value is not None:
                parts.append(f"{key}={value!r}")
        for key, value in self.props.items():
            parts.append(f"{key}={value!r}")
        if self.index:
            parts.append(f"index={self.index}")
        return " ".join(parts) if parts else "*"


def has_prop(obj: QObject, name: str) -> bool:
    return obj.metaObject().indexOfProperty(name) >= 0


def read_prop(obj: QObject, name: str):
    """安全读属性：不存在/读失败返回 None。"""
    try:
        if not has_prop(obj, name):
            return None
        return obj.property(name)
    except Exception:
        return None


def node_text(obj: QObject) -> str:
    """取节点的文本标识（属性优先级与快照一致）。"""
    for name in _TEXT_PROPS:
        value = read_prop(obj, name)
        if isinstance(value, str):
            return value
    return ""


def infer_role(obj: QObject) -> str:
    """由节点形态推断伪 a11y 角色。"""
    if has_prop(obj, "checked"):
        return "checkbox"
    cls = normalize_type(obj.metaObject().className())
    if cls.endswith("Button") or cls.endswith("Delegate"):
        return "button"
    if has_prop(obj, "text"):
        if has_prop(obj, "readOnly"):
            return "static-text" if obj.property("readOnly") else "text-input"
        if has_prop(obj, "edit") or has_prop(obj, "cursorPosition"):
            return "text-input" if not obj.property("readOnly") else "static-text"
        return "static-text"
    if has_prop(obj, "count") or has_prop(obj, "rows"):
        return "list"
    return "generic"


def iter_tree(root: QObject):
    """深度优先遍历活动对象树，产出 (obj, path)。"""
    stack: list[tuple[QObject, str]] = [(root, "0")]
    while stack:
        obj, path = stack.pop()
        yield obj, path
        children = obj.childItems() if isinstance(obj, QQuickItem) else obj.children()
        kids = list(children or [])
        for i in range(len(kids) - 1, -1, -1):
            stack.append((kids[i], f"{path}/{i}"))


def _matches(obj: QObject, path: str, selector: Selector) -> bool:
    if selector.type is not None:
        if selector.type not in normalize_type(obj.metaObject().className()):
            return False
    if selector.role is not None and infer_role(obj) != selector.role:
        return False
    if (
        selector.objectName is not None
        and read_prop(obj, "objectName") != selector.objectName
    ):
        return False
    if selector.text is not None and selector.text not in node_text(obj):
        return False
    if selector.text_equals is not None and node_text(obj) != selector.text_equals:
        return False
    if selector.path is not None and path != selector.path:
        return False
    for name, value in selector.props.items():
        if read_prop(obj, name) != value:
            return False
    return True


def resolve_all(root: QObject, selector: Selector) -> list[tuple[QObject, str]]:
    """返回全部命中节点及其路径。"""
    if not selector.context and root is None:
        return []
    return [(o, p) for o, p in iter_tree(root) if _matches(o, p, selector)]


def resolve_one(root: QObject, selector: Selector) -> tuple[QObject, str]:
    """取第 index 个命中；无命中抛 LookupError（带可读的选择器描述）。"""
    hits = resolve_all(root, selector)
    if not hits:
        raise LookupError(f"未找到节点：{selector.describe()}")
    if selector.index >= len(hits):
        raise LookupError(
            f"选择器命中 {len(hits)} 个，取不到 index={selector.index}：{selector.describe()}"
        )
    return hits[selector.index]


def describe_node(obj: QObject, path: str) -> dict:
    """节点摘要（报告里的人/agent 可读标识，避免打整棵树）。"""
    node = {
        "type": normalize_type(obj.metaObject().className()),
        "objectName": read_prop(obj, "objectName") or "",
        "path": path,
        "role": infer_role(obj),
    }
    text = node_text(obj)
    if text:
        node["text"] = text
    if isinstance(obj, QQuickItem):
        node["visible"] = bool(obj.isVisible())
        node["enabled"] = bool(obj.isEnabled())
    return node
