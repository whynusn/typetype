"""结构化报告：AI agent 的唯一消费接口（ADR-015 决策 4）。

schema 版本化，纯 JSON：可 grep、可 diff、可被 agent 直接读取。
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
