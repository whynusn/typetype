"""真机隔离的回归门禁（`tools/ui_probe/env.py`）。

背景：真机验收早期只用 `HOME=<临时目录>` 隔离。**桌面会话预置了 XDG_***
（Hyprland/Plasma/GNOME 都会导出），Qt 与 platformdirs 优先读它们——于是
"隔离"形同虚设，跑一次验收就往用户真实的 `~/.config/typetype` 与打字历史
里写一次记录。这类静默污染比崩溃更难发现，所以单独立一组门禁。
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ui_probe.env import (  # noqa: E402
    HOME_ENV,
    HOME_PREFIX,
    isolated_env,
)

#: probe 隔离 HOME 的目录名前缀——一眼可辨它是验收造的一次性目录
PROBE_PREFIX = HOME_PREFIX


def _probe_homes(report: dict) -> None:
    iso = report.get("isolation") or {}
    assert iso.get("isolated") is True, f"真机验收未在沙箱内运行：{iso}"
    home = iso.get("home")
    assert home, f"真机验收没记录沙箱 HOME：{iso}"
    assert Path(home).name.startswith(PROBE_PREFIX), (
        f"沙箱 HOME 不是一次性目录（{home}）——疑似直连了真实用户目录"
    )
    assert Path(home) != Path(os.environ.get("HOME", "")) or os.environ.get(HOME_ENV), (
        f"沙箱 HOME 与当前 HOME 相同（{home}）：隔离失效"
    )


def test_app_run_report_is_sandboxed(app_run_report):
    """真机验收必须跑在隔离 HOME 里，否则会写脏用户的配置与打字历史。"""
    _probe_homes(app_run_report)


def test_app_scenarios_are_sandboxed(scenario_suite):
    """app 模式的场景同理；component 模式不碰用户数据，不强求。"""
    for item in scenario_suite["scenarios"]:
        if item.get("mode") != "app":
            assert item.get("isolation", {}).get("isolated") in (False, None)
            continue
        _probe_homes(item)


def test_isolated_env_redirects_every_xdg_dir(tmp_path):
    """四个 XDG 目录必须全部指进沙箱——漏一个就等于没隔离。"""
    home = tmp_path / "probe-home"
    env = isolated_env(home)

    assert env["HOME"] == str(home)
    assert env["XDG_CONFIG_HOME"] == str(home / ".config")
    assert env["XDG_DATA_HOME"] == str(home / ".local" / "share")
    assert env["XDG_CACHE_HOME"] == str(home / ".cache")
    assert env["XDG_STATE_HOME"] == str(home / ".local" / "state")
    # QML 磁盘缓存会让一次运行吐出几十个文件，还可能用陈旧缓存掩盖编译错误
    assert env["QML_DISABLE_DISK_CACHE"] == "1"
    assert env[HOME_ENV] == str(home)
    # 不能污染调用者自己的环境
    assert os.environ.get("XDG_CONFIG_HOME") != str(home / ".config")
