"""P1.3 真机门禁：真实 typetype 客户端（真 Bridge/真配置/真数据）离屏启动验收。

与 mock 冒烟互补——mock 保真度覆盖不到的真实问题在此暴露：真实数据形状、
真实异步链路、真实布局。子进程隔离（Qt 不进主测试进程），并用临时 HOME
隔离真实用户配置，避免测试污染用户数据。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


@pytest.fixture(scope="module")
def app_run_report():
    # 隔离 HOME 不能放 pytest 的 tmp_path：真机启动会往 HOME 拷贝字体
    # （数 MB），而 /tmp 在本机可能是很小的 tmpfs（实测 10M → 空间不足）。
    import shutil
    import tempfile

    sandbox = Path(tempfile.mkdtemp(prefix="ui-probe-home-", dir=Path.home()))
    out = sandbox / "app_report.json"
    try:
        yield _probe_app(sandbox, out)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _probe_app(sandbox: Path, out: Path):

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TOOLS_DIR), str(REPO_ROOT), env.get("PYTHONPATH", "")]
    )
    # 隔离用户目录：真机会读写 ~/.config/typetype，测试不该碰真实配置
    env["HOME"] = str(sandbox)
    env["APPDATA"] = str(sandbox)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ui_probe.app_run",
            "--repo-root",
            str(REPO_ROOT),
            "--out",
            str(out),
            "--wait-ms",
            "1500",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert proc.returncode == 0, (
        f"真机验收子进程退出码 {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_real_client_boots_without_qml_errors(app_run_report):
    """真实客户端启动不得有 QML 错误/警告/绑定环。"""
    summary = app_run_report["summary"]
    noisy = [
        m
        for m in app_run_report["messages"]
        if m["severity"] in ("warning", "critical", "fatal")
    ]
    assert not noisy, "真实客户端产生 QML 告警:\n" + "\n".join(
        f"  [{m['severity']}] {m['message']}" for m in noisy
    )
    assert summary["binding_loops"] == 0


def test_real_client_window_renders_content(app_run_report):
    """窗口必须真的长出界面：空窗口/空树说明主 QML 没起来。"""
    window = app_run_report["window"]
    assert window["title"], "窗口标题为空——主窗口未正确初始化"
    assert window["width"] > 0 and window["height"] > 0

    def count(node) -> int:
        return 1 + sum(count(c) for c in node.get("children", []))

    nodes = count(app_run_report["tree"])
    assert nodes > 200, f"真实窗口仅 {nodes} 个节点，疑似渲染失败或快照遍历回归"
