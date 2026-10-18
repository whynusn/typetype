"""ui_probe 测试公共设施。

真机类测试（app_run / 场景 app 模式）需要一个「假 HOME」：真机会读写配置、
打字历史、字频库。隔离的坑有两层（见 `tools/ui_probe/env.py`）：

1. **不能放 /tmp** —— 真机启动会往 HOME 拷贝字体（数 MB），本机 /tmp 只有
   10M 的场合会直接写出 `[Errno 28] No space left on device`；mkdtemp 甚至会
   静默回落到 cwd 污染仓库。所以根目录固定用 `Path.home()`。
2. **光设 HOME 不够** —— 桌面会话预置了 `XDG_CONFIG_HOME` / `XDG_DATA_HOME`
   等变量，Qt 与 platformdirs 优先读它们，只改 HOME 等于没隔离。

一个 pytest 会话共用一份临时 HOME：省掉重复的字体/资源播种成本，也少删文件。
app_run / 场景两份真机报告也提到会话级——跑一次真机最贵的就是启动本身，
多个测试文件共用一份报告即可（真机报告产出后是纯 JSON 断言）。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


@pytest.fixture(scope="session")
def probe_home():
    """整个 ui_probe 测试会话共用的隔离 HOME（会话结束即删）。"""
    sandbox = Path(tempfile.mkdtemp(prefix="ui-probe-home-", dir=str(Path.home())))
    try:
        yield sandbox
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def child_env(home: Path) -> dict:
    """子进程环境：隔离 HOME + XDG_* + QML 磁盘缓存，PYTHONPATH 带上 tools。"""
    from ui_probe.env import isolated_env

    env = isolated_env(home)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TOOLS_DIR), str(REPO_ROOT), env.get("PYTHONPATH", "")]
    )
    return env


def _run_module(args: list[str], home: Path, timeout: int = 600):
    return subprocess.run(
        [sys.executable, "-m", "ui_probe.scenario", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(REPO_ROOT),
        env=child_env(home),
    )


@pytest.fixture(scope="session")
def app_run_report(probe_home):
    """真机验收报告（`ui_probe.app_run`，隔离 HOME + XDG_* 下运行）。"""
    out = probe_home / "app_report.json"
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
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        env=child_env(probe_home),
    )
    assert proc.returncode == 0, (
        f"真机验收子进程退出码 {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def scenario_suite(probe_home):
    """全部场景的报告集合（`ui_probe.scenario --all`）。"""
    out = probe_home / "scenarios.json"
    proc = _run_module(
        ["--all", "--out", str(out), "--repo-root", str(REPO_ROOT)], probe_home
    )
    assert out.exists(), (
        f"场景无报告产出（exit={proc.returncode}）：{proc.stderr[-2000:]}"
    )
    return json.loads(out.read_text(encoding="utf-8"))
