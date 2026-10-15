"""场景 DSL 门禁（ADR-015 P1.2）——子进程隔离。

与冒烟同一条纪律：**Qt 绝不进主 pytest 进程**。场景跑在独立子进程里，
报告经 JSON 回传后再断言。
"""

from __future__ import annotations

import json
import sys

from conftest import REPO_ROOT, _run_module


def test_every_scenario_passes(scenario_suite):
    """每个场景的每一步都要成立；装配失败直接算失败。"""
    assert scenario_suite["scenarios"], "没发现任何场景文件"
    problems = []
    for item in scenario_suite["scenarios"]:
        if item.get("setup_error"):
            problems.append(f"{item['name']}: 装配失败 {item['setup_error'][:200]}")
        for step in item["steps"]:
            if step["status"] == "fail":
                problems.append(
                    f"{item['name']}/{step['name']}: "
                    f"{json.dumps(step.get('detail', {}), ensure_ascii=False)[:200]}"
                )
    assert not problems, "场景步骤失败：\n" + "\n".join(problems)


def test_scenarios_are_free_of_qml_noise(scenario_suite):
    """交互过程不得产生 QML 错误/警告/绑定环（含退出期 stderr 兜底）。"""
    problems = []
    for item in scenario_suite["scenarios"]:
        summary = item["summary"]
        for key in ("errors", "warnings", "binding_loops"):
            if summary.get(key):
                messages = [
                    f"{m['severity']} {m['file']}:{m['line']} {m['message'][:140]}"
                    for m in item.get("messages", [])
                    if m["severity"] in ("warning", "critical", "fatal")
                ][:5]
                problems.append(
                    f"{item['name']}: {key}={summary[key]}\n    "
                    + "\n    ".join(messages)
                )
    assert not problems, "场景引入 QML 噪声：\n" + "\n".join(problems)


def test_scenario_engine_reports_failures_selfcheck(probe_home):
    """自检：合成必然失败的场景，引擎必须报失败（防“永远绿灯”）。"""
    proc = _run_module(["--selfcheck", "--repo-root", str(REPO_ROOT)], probe_home)
    assert proc.returncode == 0, f"自检未通过：{proc.stdout[-1500:]}"
    payload = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert payload["ok"] is True, payload
    assert payload["actual_failures"] == payload["expected_failures"]


def test_ui_report_verdict_flags_failures():
    """汇总层的判定逻辑不能是"永远绿灯"：喂进失败就得判 FAIL。"""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from ui_probe.report import build_ui_report

    clean = build_ui_report(REPO_ROOT)
    assert clean["verdict"]["passed"] is True

    dirty = build_ui_report(
        REPO_ROOT,
        smoke={
            "targets": [
                {
                    "target": "a.qml",
                    "load_errors": [],
                    "messages": [
                        {"severity": "warning", "message": "Binding loop detected"}
                    ],
                }
            ]
        },
        app_run={"summary": {"errors": 1, "warnings": 0, "binding_loops": 0}},
        scenarios={
            "scenarios": [
                {
                    "name": "s1",
                    "setup_error": None,
                    "steps": [{"status": "fail", "name": "x", "detail": {}}],
                    "summary": {"errors": 0, "warnings": 0, "binding_loops": 0},
                }
            ]
        },
        lint=[{"file": "b.qml", "line": 7, "message": "bad"}],
    )
    failures = dirty["verdict"]["failures"]
    assert dirty["verdict"]["passed"] is False
    assert any("冒烟" in f for f in failures)
    assert any("真机" in f for f in failures)
    assert any("场景" in f for f in failures)
    assert any("静态规则" in f for f in failures)


def test_no_window_attached_property_inside_connections():
    """静态规则：Connections 内不得引用 Window.window。

    这类写法 qmllint 抓不到（类型合法），运行时每次信号分发报一次警告
    ——实测一轮打字刷 900+ 条。静态拦下最便宜。
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from ui_probe.lint import scan_tree

    findings = scan_tree(REPO_ROOT)
    assert not findings, "Connections 内引用了 Item 附加属性：\n" + "\n".join(
        f"{f['file']}:{f['line']} {f['snippet']}" for f in findings
    )
