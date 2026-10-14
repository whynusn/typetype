"""真机验收（P1.3）：启动**真实** typetype 客户端并在离屏环境做验收。

与冒烟（mock bridge）的差别：真 Bridge、真配置、真实数据、真实异步 worker
——mock 保真度覆盖不到的真实问题（真实数据形状、真实绑定、真实布局）在此暴露。

    python -m ui_probe.app_run --out app_report.json [--wait-ms 1500]

产物 schema ``ui-probe/app-run@1``：窗口对象树快照 + 捕获到的 QML 消息 +
汇总计数。与 mock 冒烟互补，同为 AI agent 的结构化消费接口。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop

from .message_capture import MessageCollector
from .snapshot import SnapshotOptions, snapshot_node

APP_RUN_SCHEMA = "ui-probe/app-run@1"


def run_app_probe(
    repo_root: Path,
    wait_ms: int = 1500,
    platform: str = "offscreen",
    max_nodes: int = 6000,
) -> dict:
    """启动真实 app，跑一段事件循环，返回快照报告。"""
    repo_root = Path(repo_root).resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from main import bootstrap, shutdown  # noqa: PLC0415  （需 repo_root 在 sys.path 上）

    started = time.monotonic()
    with MessageCollector() as collector:
        runtime = bootstrap(argv=[sys.argv[0], "-platform", platform])

        # 让异步链路跑一会：定时器、worker（载文/统计/字体）、延迟绑定等都
        # 在事件循环里完成——快照太早会拍到"还没长出来"的界面。
        deadline = time.monotonic() + wait_ms / 1000.0
        while time.monotonic() < deadline:
            runtime.app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

        root_window = runtime.window.root_window
        root_item = (
            root_window.contentItem()
            if hasattr(root_window, "contentItem")
            else root_window
        )
        options = SnapshotOptions(max_nodes=max_nodes)
        tree = snapshot_node(root_item, "0", 0, options)
        window_info = {
            "title": str(root_window.property("title") or ""),
            "width": float(root_window.width()),
            "height": float(root_window.height()),
            "visible": bool(root_window.isVisible()),
        }
        messages = collector.messages

    payload = {
        "schema": APP_RUN_SCHEMA,
        "repo_root": str(repo_root),
        "platform": platform,
        "wait_ms": wait_ms,
        "window": window_info,
        "tree": tree,
        "messages": [
            {
                "severity": m.severity,
                "category": m.category,
                "message": m.message,
                "file": m.file,
                "line": m.line,
            }
            for m in messages
        ],
        "summary": {
            "duration_ms": int((time.monotonic() - started) * 1000),
            "errors": sum(1 for m in messages if m.severity in ("critical", "fatal")),
            "warnings": sum(1 for m in messages if m.severity == "warning"),
            "binding_loops": sum(1 for m in messages if "Binding loop" in m.message),
        },
    }
    shutdown(runtime)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ui-probe 真机验收（真实客户端）")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument(
        "--wait-ms", type=int, default=1500, help="事件循环运行时间（毫秒）"
    )
    parser.add_argument(
        "--platform", default="offscreen", help="Qt 平台插件（默认 offscreen）"
    )
    parser.add_argument("--pretty", action="store_true", help="缩进输出（默认紧凑）")
    args = parser.parse_args(argv)

    payload = run_app_probe(
        Path(args.repo_root).resolve(),
        wait_ms=args.wait_ms,
        platform=args.platform,
    )
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        s = payload["summary"]
        print(
            f"真机验收：错误 {s['errors']}，警告 {s['warnings']}，"
            f"绑定环 {s['binding_loops']}，耗时 {s['duration_ms']}ms -> {args.out}"
        )
    else:
        print(text)

    # 与 main.py 一致：直接退出，避免 Qt/worker 静态析构期的崩溃
    sys.stdout.flush()
    os._exit(1 if payload["summary"]["errors"] else 0)


if __name__ == "__main__":
    main()
