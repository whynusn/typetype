"""P1.1 快照门禁：全部 QML 目标都必须能产出结构化对象树（ADR-015 决策 3）。

快照是"AI 读前端"与结构化断言的底座；目标拿不到树 = 断言链路断裂。
与冒烟同样走子进程隔离（Qt 不进主测试进程）。
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

from ui_probe.smoke import discover_targets  # noqa: E402


@pytest.fixture(scope="module")
def snapshot_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("ui-probe-snap") / "snapshot.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TOOLS_DIR), str(REPO_ROOT), env.get("PYTHONPATH", "")]
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ui_probe.snapshot",
            "--repo-root",
            str(REPO_ROOT),
            "--all",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
    )
    assert proc.returncode == 0, (
        f"快照子进程退出码 {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    import json

    return json.loads(out.read_text(encoding="utf-8"))


def test_snapshot_covers_all_targets(snapshot_report):
    """快照覆盖面与冒烟一致：漏一个目标就少一条断言链路。"""
    expected = {
        p.relative_to(REPO_ROOT).as_posix() for p in discover_targets(REPO_ROOT)
    }
    got = {t["target"] for t in snapshot_report["targets"]}
    assert not expected - got, f"未快照的目标: {sorted(expected - got)}"


def test_snapshot_all_targets_have_tree(snapshot_report):
    """每个目标都必须拿到对象树（拿不到 = 组件不可内省，断言无从谈起）。"""
    failed = [t["target"] for t in snapshot_report["targets"] if not t.get("root")]
    assert not failed, f"以下目标未产出对象树: {failed}"


def test_snapshot_pages_are_composite(snapshot_report):
    """页面级目标的树必须有实质内容。

    叶子型组件（如 EmptyState 就是一个 Text）本就只有 1 个节点，不能一律
    要求"复杂"；但页面必然是复合 UI——若遍历逻辑回归（childItems 取不到
    等），页面节点数会崩塌到个位数。
    """
    pages = [
        (t["target"], t["node_count"])
        for t in snapshot_report["targets"]
        if "/pages/" in t["target"]
    ]
    assert pages, "未发现页面级目标——发现逻辑可能回归"
    thin = [(t, n) for t, n in pages if n < 50]
    assert not thin, f"以下页面节点数异常偏少（疑似遍历回归）: {thin}"
