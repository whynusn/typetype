"""独立加载时的属性注入（fixtures）。

部分组件依赖父级注入的状态才能在离屏环境实例化：如 FontManagerDialog 的
``fontModel`` 在真实运行时由 SettingsPage 传入 ListModel 实例，孤立加载时
为 null，其 ``.count`` 绑定抛 TypeError——这是 harness 的隔离噪声，不是
产品缺陷。与其在报告里掩口噪声，不如显式声明"该组件独立加载需要这些输入"。

fixtures.json（默认 tools/ui_probe/fixtures.json）按目标相对路径声明：

    {
      "src/qml/settings/FontManagerDialog.qml": {
        "fontModel": {"$listmodel": true}
      }
    }

取值形式：
- JSON 原语 / 数组：直接作为 createObject 初始属性
- ``{"$listmodel": true}``：空 ListModel 实例（满足 QML 的 .count/.get 契约）
- ``{"$qml": "<expr>"}``：在 engine root context 求值的 JS 表达式（逃生舱口）

key 必须是目标相对仓库的路径；目标被移动/重命名后 fixture 静默失效，
由 tests/ui_probe/test_qml_smoke.py::test_fixture_keys_match_targets 兜底。
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQml import QJSValue


DEFAULT_FIXTURES_RELPATH = "tools/ui_probe/fixtures.json"

_LISTMODEL_QML = "import QtQml.Models 2.15\nListModel {}"


def load_fixtures(path: Path) -> dict[str, dict]:
    """读取 fixtures.json；文件不存在视为无注入。"""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"fixtures 文件顶层应为对象: {path}")
    return data


def fixtures_for_target(fixtures: dict[str, dict], target_rel: str) -> dict:
    """按目标相对路径取注入属性表；未命中返回空。"""
    return fixtures.get(target_rel, {})


def unused_fixture_keys(fixtures: dict[str, dict], target_rels: set[str]) -> list[str]:
    """找出对不上任何目标的 fixture key（目标被移动/重命名的信号）。"""
    return sorted(set(fixtures) - target_rels)


def resolve_fixture_value(engine: QQmlEngine, spec: object) -> object:
    """把 JSON fixture 值解析为可注入 createObject 的 Qt/QML 值。"""
    if isinstance(spec, dict):
        if "$listmodel" in spec:
            return _create_list_model(engine)
        if "$qml" in spec:
            return _evaluate_expression(engine, str(spec["$qml"]))
        raise ValueError(
            f"未知 fixture 形式: {spec!r}（支持 $listmodel / $qml / JSON 原语）"
        )
    return spec


def _create_list_model(engine: QQmlEngine) -> object:
    component = QQmlComponent(engine)
    component.setData(_LISTMODEL_QML.encode("utf-8"), QUrl())
    instance = component.create()
    if instance is None:
        errors = "; ".join(str(e.description()) for e in component.errors())
        raise RuntimeError(f"ListModel 创建失败: {errors}")
    return instance


def _evaluate_expression(engine: QQmlEngine, expression: str) -> object:
    expression_obj = QQmlExpression(engine.rootContext(), None, expression)
    value = expression_obj.evaluate()
    if expression_obj.hasError():
        raise RuntimeError(
            f"fixture 表达式求值失败: {expression!r}: {_error_text(expression_obj)}"
        )
    if isinstance(value, QJSValue):
        value = value.toVariant()
    return value


def _error_text(expression_obj: QQmlExpression) -> str:
    error = expression_obj.error()
    to_string = getattr(error, "toString", None)
    if callable(to_string):
        return str(to_string())
    return str(getattr(error, "description", lambda: error)())
