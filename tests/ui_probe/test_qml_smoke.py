"""P0 冒烟测试：离屏加载全部 QML 页面/组件（ADR-015）。

执行方式为**子进程隔离**：冒烟在独立 python 进程里跑（``-m ui_probe.smoke``），
报告经 JSON 文件回传。原因：Qt/shiboken 一旦在主测试进程初始化，其退出期
静态析构会与后台 daemon 线程（OTT 跨仓测试的 socketserver）冲突，
实测全量 pytest 跑到 100% 后 SIGABRT——隔离是唯一可靠解。

门禁（任一不过即失败）：
- 发现覆盖度：src/qml 下全部非 singleton .qml 都必须被加载
- 加载失败（如 RinUI 模块外未解析类型，ItemDelegate 类回归）
- 加载期纯 QML 绑定环（经 appBridge 往返的环归 P1 场景驱动，见 ADR-015）
- 任何 warning/critical 消息：mock bridge 保真后应无残留，新警告按回归处理
- fixture key 必须对得上真实目标（目标移动/重命名后静默失效的兜底）
- 绑定环检测器自检：合成已知环必须被抓获（防检测机制静默失效）

运行单个文件：``uv run pytest tests/ui_probe/test_qml_smoke.py -q``
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ui_probe.fixtures import (  # noqa: E402
    DEFAULT_FIXTURES_RELPATH,
    load_fixtures,
    unused_fixture_keys,
)
from ui_probe.report import load_report  # noqa: E402
from ui_probe.smoke import _singleton_files  # noqa: E402


def _run_ui_probe(*args: str) -> subprocess.CompletedProcess:
    """在隔离子进程里执行 ui-probe CLI。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TOOLS_DIR), str(REPO_ROOT), env.get("PYTHONPATH", "")]
    )
    return subprocess.run(
        [sys.executable, "-m", "ui_probe.smoke", "--repo-root", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


@pytest.fixture(scope="module")
def smoke_report(tmp_path_factory):
    report_path = tmp_path_factory.mktemp("ui-probe") / "ui_report.json"
    proc = _run_ui_probe("--report", str(report_path))
    assert proc.returncode == 0, (
        f"ui-probe 冒烟子进程退出码 {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert report_path.exists(), f"冒烟子进程未产出报告: {proc.stderr}"
    return load_report(report_path)


def test_discovery_covers_all_qml_files(smoke_report):
    """覆盖度自检：src/qml 下全部非 singleton .qml 都应被发现。

    发现逻辑回归（rglob 根目录漂移、过滤过宽）会让目标数悄悄变少，
    加载失败/绑定环类回归随之失去被抓的机会。
    """
    expected = {
        str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "src/qml").rglob("*.qml")
    } - {str(p.relative_to(REPO_ROOT)) for p in _singleton_files(REPO_ROOT)}
    discovered = {t["target"] for t in smoke_report.targets}
    missing = expected - discovered
    assert not missing, f"以下 QML 文件未被冒烟覆盖: {sorted(missing)}"


def test_qml_targets_discovered(smoke_report):
    """目标数量级自检：当前 30+，防止发现逻辑静默失效。"""
    assert smoke_report.summary["total"] >= 30, (
        f"仅发现 {smoke_report.summary['total']} 个 QML 目标，"
        "发现逻辑可能回归（目录移动/qmldir 变更）"
    )


def test_no_qml_load_errors(smoke_report):
    """所有页面/组件必须能离屏实例化（抓 ItemDelegate 类回归）。"""
    failures = smoke_report.failed_targets
    assert not failures, _format_failures(failures, "加载失败")


def test_no_binding_loops(smoke_report):
    """加载期不得出现纯 QML 绑定环（如属性互依赖）。

    覆盖边界：经 appBridge 往返的绑定环（checked → setX → XChanged →
    绑定重算）需要真实初始值≠QML 默认值才会在加载期显形，被动 mock
    无法复现——该类归入 P1 场景驱动（种子状态 + 交互）范畴。
    """
    looping = smoke_report.binding_loop_targets
    assert not looping, _format_failures(looping, "绑定环")


def test_no_unexpected_warnings(smoke_report):
    """零警告门禁：mock bridge 保真后应无 warning/critical 残留。

    新警告 = 新回归或新的隔离噪声。处理方式：修产品代码，或在
    tools/ui_probe/fixtures.json 为依赖父级状态的组件补 fixture。
    """
    noisy = [
        t
        for t in smoke_report.targets
        if any(m["severity"] in ("warning", "critical", "fatal") for m in t["messages"])
    ]
    assert not noisy, _format_failures(noisy, "警告")


def test_fixture_keys_match_targets(smoke_report):
    """fixtures.json 的 key 必须对得上真实目标。

    目标被移动/重命名后 fixture 静默失效，对应组件回到 null 注入、
    警告重新出现——本测试把这种"静默"变成显式失败。
    """
    fixtures = load_fixtures(REPO_ROOT / DEFAULT_FIXTURES_RELPATH)
    stale = unused_fixture_keys(fixtures, {t["target"] for t in smoke_report.targets})
    assert not stale, (
        f"以下 fixture key 对不上任何冒烟目标（目标被移动/重命名？）: {stale}"
    )


def test_binding_loop_detector_selfcheck():
    """检测器自检（子进程）：合成已知绑定环必须被 harness 抓获。

    防消息捕获/判定逻辑静默失效——自检先失败，而不是放跑所有真环。
    """
    proc = _run_ui_probe("--selfcheck-loop")
    assert proc.returncode == 0, (
        f"绑定环检测器自检失败（退出码 {proc.returncode}）\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )


def _format_failures(targets: list[dict], label: str) -> str:
    lines = [f"{len(targets)} 个目标存在{label}："]
    for target in targets:
        lines.append(f"  - {target['target']}")
        for err in target.get("load_errors", []):
            lines.append(
                f"      error: {err['message']} (:{err['line']}:{err['column']})"
            )
        for msg in target.get("messages", []):
            if label == "绑定环" and "Binding loop" not in msg["message"]:
                continue
            lines.append(f"      {msg['severity']}: {msg['message']}")
    return "\n".join(lines)
