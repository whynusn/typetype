"""一键验收：跑齐全部层次，产出 ``ui_report.json``（ADR-015 决策 4）。

    python -m ui_probe.suite --out ui_report.json

层次与职责：

| 层 | 命令 | 抓什么 |
|:--|:--|:--|
| 冒烟 | ``ui_probe.smoke`` | 全量 QML 加载错误 / 绑定环 / qWarning（mock bridge） |
| 快照 | ``ui_probe.snapshot`` | 结构化对象树（几何/可见性/文本）基线 |
| 真机 | ``ui_probe.app_run`` | 真实客户端启动与窗口渲染 |
| 场景 | ``ui_probe.scenario`` | 声明式交互流程（打字/重打/统计） |
| 静态 | ``ui_probe.lint`` | qmllint 抓不到的作用域类缺陷 |

**每层一个独立子进程**：Qt 在一个进程里起第二个真实客户端状态会串，
且退出期静态析构与后台线程冲突会 SIGABRT（实测）。报告经 JSON 回传。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .lint import scan_tree
from .report import build_ui_report

# 冒烟/快照/真机各自一个子进程；场景由本进程逐个起子进程
_STAGES = {
    # smoke 没有 --all：它默认就是全量
    "smoke": ["-m", "ui_probe.smoke", "--report"],
    "snapshot": ["-m", "ui_probe.snapshot", "--all", "--out"],
    "app_run": ["-m", "ui_probe.app_run", "--out"],
}


def _run_stage(name: str, repo_root: Path, workdir: Path) -> dict | None:
    out = workdir / f"{name}.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root / "tools"), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, *_STAGES[name], str(out), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(repo_root),
        env=env,
    )
    if not out.exists():
        # 层跑不起来必须算失败：静默跳过一层会让判定一路绿灯，
        # 而恰恰是"没跑到的那层"才最容易藏问题。
        print(f"[{name}] 无报告产出（exit={proc.returncode}）", file=sys.stderr)
        print(proc.stderr[-1500:], file=sys.stderr)
        return {"stage_error": f"exit={proc.returncode}: {proc.stderr[-300:]}"}
    print(f"[{name}] ok -> {out.name}")
    return json.loads(out.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ui-probe 一键验收（产出 ui_report.json）"
    )
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--out", default="ui_report.json", help="输出 JSON 路径")
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="跳过的层（可多次：smoke/snapshot/app_run/scenarios）",
    )
    parser.add_argument("--pretty", action="store_true", help="缩进输出")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    skip = set(args.skip)
    # 临时目录放 HOME 而非 /tmp：真机启动会往 HOME 拷字体（数 MB），
    # 且沙箱 /tmp 常常只有 10M，落在 /tmp 会直接 ENOSPC。
    workdir = Path(tempfile.mkdtemp(prefix="ui-probe-suite-", dir=str(Path.home())))
    try:
        smoke = None if "smoke" in skip else _run_stage("smoke", repo_root, workdir)
        snapshot = (
            None if "snapshot" in skip else _run_stage("snapshot", repo_root, workdir)
        )
        app_run = (
            None if "app_run" in skip else _run_stage("app_run", repo_root, workdir)
        )

        scenarios = None
        if "scenarios" not in skip:
            sys.path.insert(0, str(repo_root / "tools"))
            from .scenario import discover_scenarios, run_scenario_isolated

            reports = [
                run_scenario_isolated(p, repo_root)
                for p in discover_scenarios(repo_root)
            ]
            scenarios = {
                "schema": "ui-probe/scenario@1",
                "repo_root": str(repo_root),
                "scenarios": reports,
                "summary": {
                    "total": len(reports),
                    "passed": sum(
                        1
                        for r in reports
                        if not r["summary"]["failed"] and not r["setup_error"]
                    ),
                    "failed": sum(
                        1 for r in reports if r["summary"]["failed"] or r["setup_error"]
                    ),
                },
            }
            print(
                f"[scenarios] ok -> {scenarios['summary']['passed']}/{scenarios['summary']['total']} 通过"
            )

        lint = scan_tree(repo_root)
        print(f"[lint] {len(lint)} 条")

        payload = build_ui_report(
            repo_root,
            smoke=smoke,
            snapshot=snapshot,
            app_run=app_run,
            scenarios=scenarios,
            lint=lint,
        )
        payload["generated_at"] = (
            datetime.now().astimezone().isoformat(timespec="seconds")
        )
        # 层未跑起来 = 未验收，不能算通过
        for name, payload_section in payload["sections"].items():
            if isinstance(payload_section, dict) and payload_section.get("stage_error"):
                payload["verdict"]["failures"].insert(
                    0, f"层 {name} 未跑起来：{payload_section['stage_error'][:200]}"
                )
        payload["verdict"]["passed"] = not payload["verdict"]["failures"]

        out = Path(args.out)
        if not out.is_absolute():
            out = repo_root / out
        out.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
                separators=None if args.pretty else (",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        verdict = payload["verdict"]
        print(
            f"\n判定：{'PASS' if verdict['passed'] else 'FAIL'}（{len(verdict['failures'])} 项问题）"
        )
        for item in verdict["failures"][:20]:
            print(f"  - {item}")
        print(f"-> {out}")
        return 0 if verdict["passed"] else 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
