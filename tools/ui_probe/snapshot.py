"""结构化快照：QQuickItem 树 + 属性（ADR-015 决策 3 的主力断言基底）。

CLI：
    python -m ui_probe.snapshot --target src/qml/pages/TypingPage.qml
    python -m ui_probe.snapshot --all --out snapshot.json


直接读 QML 对象树与属性，**绕开 AT-SPI value 读回不可靠**的问题
（CU 栈实测：统计类文本经 AT-SPI 读回失真）。输出纯 JSON，可 grep/diff，
供 AI agent 阅读与场景断言消费。

选择器语义（快照即"前端的 DOM 视图"）：
- ``objectName``：本项目绝大多数节点**为空**（QML 习惯不设），只在有值时可用
- ``type``：归一化后的 QML 类型名（`WeakCharsPage_QMLTYPE_92` → `WeakCharsPage`）
- ``text`` / 属性：文本类节点的稳定标识
- ``path``：树内索引路径（`0/2/1`），形状变化时比文本更稳
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QPointF
from PySide6.QtQuick import QQuickItem

from .loader import OffscreenHarness
from .smoke import discover_targets


# `Foobar_QMLTYPE_92` / `QQuickItem_QML_35` → `Foobar` / `QQuickItem`
_QML_TYPE_SUFFIX = re.compile(r"_(?:QMLTYPE|QML)_\d+$")

# 默认捕获的属性（存在才写入）
_DEFAULT_PROPS = (
    "text",
    "title",
    "label",
    "description",
    "placeholderText",
    "checked",
    "value",
    "currentIndex",
    "count",
    "progress",
)

# 快照里承担标识作用的属性（单独提升到顶层，便于断言/选择器）
_TEXT_PROPS = ("text", "title", "label", "description", "placeholderText")


@dataclass
class SnapshotOptions:
    """快照选项。"""

    root_width: int = 1280  # 离屏没有窗口，需显式给根节点尺寸才会触发布局
    root_height: int = 800
    size_root: bool = True  # 是否强制根节点为视口尺寸（根无父级，绑定位无害）
    max_depth: int = 32
    max_nodes: int = 4000
    extra_props: tuple[str, ...] = ()


@dataclass
class SnapshotResult:
    """单个目标的快照结果。"""

    target: str
    root: dict | None = None
    truncated: bool = False
    node_count: int = 0
    load_errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "root": self.root,
            "truncated": self.truncated,
            "node_count": self.node_count,
            "load_errors": self.load_errors,
        }


def normalize_type(class_name: str) -> str:
    """归一化 QML 类型名（去掉引擎加的 _QMLTYPE_n 后缀）。"""
    return _QML_TYPE_SUFFIX.sub("", class_name or "")


def _scene_bounds(item: QQuickItem) -> dict:
    """取场景坐标下的包围盒（断言几何比局部坐标更有意义）。"""
    point = item.mapToScene(QPointF(0, 0))
    return {
        "x": round(point.x(), 2),
        "y": round(point.y(), 2),
        "w": round(item.width(), 2),
        "h": round(item.height(), 2),
    }


def _read_prop(obj: QObject, name: str):
    """安全读属性：不存在/读失败都返回 None。"""
    try:
        index = obj.metaObject().indexOfProperty(name)
        if index < 0:
            return None
        return obj.property(name)
    except Exception:
        return None


def _jsonable(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def snapshot_node(
    obj: QObject,
    path: str = "0",
    depth: int = 0,
    options: SnapshotOptions | None = None,
    counter: list[int] | None = None,
) -> dict:
    """递归序列化单个节点。"""
    options = options or SnapshotOptions()
    counter = counter if counter is not None else [0]
    counter[0] += 1

    node: dict = {
        "type": normalize_type(obj.metaObject().className()),
        "objectName": _jsonable(_read_prop(obj, "objectName")) or "",
        "path": path,
    }

    if isinstance(obj, QQuickItem):
        node["bounds"] = _scene_bounds(obj)
        node["visible"] = bool(obj.isVisible())
        node["enabled"] = bool(obj.isEnabled())
        node["opacity"] = round(float(obj.opacity()), 3)

    props: dict = {}
    for name in _DEFAULT_PROPS + tuple(options.extra_props):
        value = _read_prop(obj, name)
        if value is None:
            continue
        props[name] = _jsonable(value)
    for name in _TEXT_PROPS:
        if name in props:
            node["text"] = props.pop(name)
            break
    if props:
        node["props"] = props

    if depth >= options.max_depth or counter[0] >= options.max_nodes:
        return node

    children = obj.childItems() if isinstance(obj, QQuickItem) else obj.children()
    if children:
        node["children"] = [
            snapshot_node(child, f"{path}/{i}", depth + 1, options, counter)
            for i, child in enumerate(children)
        ]
    return node


def snapshot_target(
    harness: OffscreenHarness,
    qml_path: Path,
    options: SnapshotOptions | None = None,
    fixture_specs: dict | None = None,
) -> SnapshotResult:
    """加载目标并快照其对象树。"""
    options = options or SnapshotOptions()
    qml_path = Path(qml_path)
    try:
        target = qml_path.relative_to(harness.repo_root).as_posix()
    except ValueError:
        target = str(qml_path)

    result = harness.load(qml_path, fixture_specs=fixture_specs)
    if not result.ok or not harness._instances:
        return SnapshotResult(target=target, root=None, load_errors=result.load_errors)

    root_obj = harness._instances[-1]
    # 离屏无窗口：根节点是内容尺寸（如 112x24），内部布局无从解算。
    # 强制为视口尺寸后，Layout/anchors 才有意义地展开。根无父级，
    # 覆写其 width/height 绑定（若有）无副作用。
    if options.size_root and isinstance(root_obj, QQuickItem):
        root_obj.setWidth(options.root_width)
        root_obj.setHeight(options.root_height)

    counter = [0]
    root = snapshot_node(root_obj, "0", 0, options, counter)
    return SnapshotResult(
        target=target,
        root=root,
        truncated=counter[0] >= options.max_nodes,
        node_count=counter[0],
        load_errors=result.load_errors,
    )


SNAPSHOT_SCHEMA = "ui-probe/snapshot@1"


def build_snapshot_report(results: list[SnapshotResult], repo_root: Path) -> dict:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "repo_root": str(repo_root),
        "targets": [r.to_dict() for r in results],
        "summary": {
            "total": len(results),
            "failed": sum(1 for r in results if r.root is None),
            "nodes": sum(r.node_count for r in results),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ui-probe 结构化快照")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument(
        "--target", action="append", default=[], help="目标 QML（可多次指定）"
    )
    parser.add_argument("--all", action="store_true", help="快照全部冒烟目标")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="缩进输出（默认紧凑：全量快照用缩进会大到数十 MB）",
    )
    parser.add_argument("--root-width", type=int, default=1280)
    parser.add_argument("--root-height", type=int, default=800)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    targets = (
        discover_targets(repo_root)
        if args.all
        else [repo_root / t for t in args.target]
    )
    if not targets:
        print("未指定目标（--target 或 --all）", file=sys.stderr)
        return 2

    options = SnapshotOptions(root_width=args.root_width, root_height=args.root_height)
    harness = OffscreenHarness(repo_root)
    results: list[SnapshotResult] = []
    try:
        for path in targets:
            results.append(snapshot_target(harness, path, options))
    finally:
        harness.close()

    payload = build_snapshot_report(results, repo_root)
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(
            f"快照：{payload['summary']['total']} 个目标，"
            f"{payload['summary']['nodes']} 个节点，写入 {args.out}"
        )
    else:
        print(text)
    return 1 if payload["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
