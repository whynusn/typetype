"""真机验收（P1.3）：启动**真实** typetype 客户端并在离屏环境做验收。

与冒烟（mock bridge）的差别：真 Bridge、真配置、真实数据、真实异步 worker
——mock 保真度覆盖不到的真实问题（真实数据形状、真实绑定、真实布局）在此暴露。

    python -m ui_probe.app_run --out app_report.json [--wait-ms 1500]

产物 schema ``ui-probe/app-run@1``：窗口对象树快照 + 捕获到的 QML 消息 +
汇总计数。与 mock 冒烟互补，同为 AI agent 的结构化消费接口。

**默认隔离真机的数据目录**（见 `env.py`）：桌面会话预置的 XDG_* 会让"只改
HOME"的隔离形同虚设，配置与打字历史会直接写进用户真实目录。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop

from .env import dispose_owned_homes, enter_sandbox
from .message_capture import MessageCollector
from .snapshot import SnapshotOptions, snapshot_node

APP_RUN_SCHEMA = "ui-probe/app-run@1"


def run_app_probe(
    repo_root: Path,
    wait_ms: int = 1500,
    platform: str = "offscreen",
    max_nodes: int = 6000,
    isolated: bool = True,
) -> dict:
    """启动真实 app，跑一段事件循环，返回快照报告。

    isolated=True（默认）时先把自己隔离进临时 HOME + XDG_*，不碰用户数据。
    """
    repo_root = Path(repo_root).resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 必须早于 import main：bootstrap 期间就会解析配置/数据目录
    sandbox_home = enter_sandbox() if isolated else None

    from main import bootstrap, shutdown  # noqa: PLC0415  （需 repo_root 在 sys.path 上）

    started = time.monotonic()
    collector = MessageCollector()
    # 覆盖窗口一（bootstrap 期）：app 会顶掉 Qt handler，靠 logging sink 捞
    collector.install()
    collector.attach_log_sink()
    try:
        runtime = bootstrap(argv=[sys.argv[0], "-platform", platform])
        # 覆盖窗口二（bootstrap 之后）：夺回 Qt handler 并转发给 app 的 handler
        collector.detach_log_sink()
        collector.reinstall()

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
        messages = list(collector.messages)
        before_shutdown = len(messages)
        # 退出期同样纳入验收：实测真机在 shutdown 阶段会抛
        # "QThread: Destroyed while thread is still running"——只拍快照不看
        # 退出，这条真实缺陷就永远抓不到。
        shutdown(runtime)
        messages = list(collector.messages)
        shutdown_messages = messages[before_shutdown:]
    finally:
        collector.uninstall()

    def count(items, predicate) -> int:
        return sum(1 for m in items if predicate(m))

    payload = {
        "schema": APP_RUN_SCHEMA,
        "repo_root": str(repo_root),
        "platform": platform,
        "wait_ms": wait_ms,
        "window": window_info,
        # 透明性：真机模式必须跑在一次性 HOME 里，否则会写脏用户真实数据
        "isolation": {
            "isolated": isolated,
            "home": str(sandbox_home) if sandbox_home else None,
        },
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
            "errors": count(messages, lambda m: m.severity in ("critical", "fatal")),
            "warnings": count(messages, lambda m: m.severity == "warning"),
            "binding_loops": count(messages, lambda m: "Binding loop" in m.message),
            "errors_during_shutdown": count(
                shutdown_messages, lambda m: m.severity in ("critical", "fatal")
            ),
            "warnings_during_shutdown": count(
                shutdown_messages, lambda m: m.severity == "warning"
            ),
        },
    }
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
    parser.add_argument(
        "--no-isolate",
        action="store_true",
        help="不隔离 HOME/XDG_*（直接读写真实用户配置与打字数据，仅供排查真实数据问题时用）",
    )
    args = parser.parse_args(argv)

    payload = run_app_probe(
        Path(args.repo_root).resolve(),
        wait_ms=args.wait_ms,
        platform=args.platform,
        isolated=not args.no_isolate,
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

    # 与 main.py 一致：硬退出绕开 Qt/worker 静态析构期的崩溃。
    # 代价是 atexit 不跑——沙箱 HOME 必须自己先收拾干净，否则每次验收都
    # 在 ~/ 下留一个跑过真机的目录。
    dispose_owned_homes()
    sys.stdout.flush()
    os._exit(1 if payload["summary"]["errors"] else 0)


if __name__ == "__main__":
    main()
