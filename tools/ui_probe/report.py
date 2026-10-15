"""结构化报告：AI agent 的唯一消费接口（ADR-015 决策 4）。

schema 版本化，纯 JSON：可 grep、可 diff、可被 agent 直接读取。
``build_ui_report`` 产出跨层汇总的 ``ui-probe/report@1``（即 ui_report.json）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .loader import LoadResult


REPORT_SCHEMA = "ui-probe/report@1"


@dataclass
class SmokeReport:
    schema: str
    repo_root: str
    targets: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> SmokeReport:
        """从 JSON 报告还原（子进程跑冒烟、父进程断言的传输格式）。"""
        return cls(
            schema=data["schema"],
            repo_root=data["repo_root"],
            targets=data.get("targets", []),
            summary=data.get("summary", {}),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def write(self, path: Path) -> None:
        path.write_text(self.to_json() + "\n", encoding="utf-8")

    @property
    def failed_targets(self) -> list[dict]:
        return [t for t in self.targets if t["load_errors"]]

    @property
    def binding_loop_targets(self) -> list[dict]:
        return [
            t
            for t in self.targets
            if any("Binding loop" in m["message"] for m in t["messages"])
        ]


UI_REPORT_SCHEMA = "ui-probe/report@1"
"""统一报告 ``ui_report.json`` 的 schema（ADR-015 决策 4）。

AI agent 的**唯一**消费入口：把冒烟 / 快照 / 真机 / 场景 / 静态规则五层的
结果汇成一份可 grep、可 diff 的 JSON。
"""


def build_ui_report(
    repo_root: Path,
    smoke: dict | None = None,
    snapshot: dict | None = None,
    app_run: dict | None = None,
    scenarios: dict | None = None,
    lint: list[dict] | None = None,
) -> dict:
    """聚合各层结果为 ``ui-probe/report@1``。"""
    failures: list[str] = []

    if smoke:
        for target in smoke.get("targets", []):
            if target.get("load_errors"):
                failures.append(f"冒烟加载失败：{target['target']}")
            for message in target.get("messages", []):
                if message["severity"] in ("warning", "critical", "fatal"):
                    failures.append(
                        f"冒烟 {message['severity']}：{target['target']} — {message['message'][:120]}"
                    )
    if snapshot:
        for target in snapshot.get("targets", []):
            if target.get("root") is None:
                failures.append(f"快照失败：{target['target']}")
    if app_run:
        summary = app_run.get("summary", {})
        for key in ("errors", "warnings", "binding_loops"):
            if summary.get(key):
                failures.append(f"真机 {key}={summary[key]}")
    if scenarios:
        for item in scenarios.get("scenarios", []):
            if item.get("setup_error"):
                failures.append(
                    f"场景 {item['name']} 装配失败：{item['setup_error'][:160]}"
                )
            for step in item.get("steps", []):
                if step["status"] == "fail":
                    failures.append(
                        f"场景 {item['name']} 步骤失败：{step['name']} — "
                        f"{json.dumps(step.get('detail', {}), ensure_ascii=False)[:160]}"
                    )
            summary = item.get("summary", {})
            for key in ("errors", "warnings", "binding_loops"):
                if summary.get(key):
                    failures.append(f"场景 {item['name']} {key}={summary[key]}")
    for finding in lint or []:
        failures.append(
            f"静态规则：{finding['file']}:{finding['line']} — {finding['message']}"
        )

    return {
        "schema": UI_REPORT_SCHEMA,
        "repo_root": str(repo_root),
        "sections": {
            "smoke": smoke,
            "snapshot": snapshot,
            "app_run": app_run,
            "scenarios": scenarios,
            "lint": lint or [],
        },
        "verdict": {"passed": not failures, "failures": failures},
    }


def load_report(path: Path) -> SmokeReport:
    """从 JSON 报告文件还原 SmokeReport。"""
    return SmokeReport.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def build_report(repo_root: Path, results: list[LoadResult]) -> SmokeReport:
    targets = []
    for result in results:
        targets.append(
            {
                "target": result.target,
                "ok": result.ok,
                "load_errors": result.load_errors,
                "fixtures": result.fixtures,
                "messages": [
                    {
                        "severity": m.severity,
                        "category": m.category,
                        "message": m.message,
                        "file": m.file,
                        "line": m.line,
                    }
                    for m in result.messages
                ],
            }
        )
    report = SmokeReport(
        schema=REPORT_SCHEMA,
        repo_root=str(repo_root),
        targets=targets,
    )
    report.summary = {
        "total": len(targets),
        "load_failed": len(report.failed_targets),
        "binding_loops": len(report.binding_loop_targets),
        "warnings": sum(
            1
            for t in targets
            for m in t["messages"]
            if m["severity"] in ("warning", "critical", "fatal")
        ),
    }
    return report
