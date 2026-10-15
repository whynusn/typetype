"""真机运行环境的隔离（HOME + XDG_* + QML 磁盘缓存）。

## 为什么不是"设个 HOME 就够了"

桌面会话普遍预置 ``XDG_CONFIG_HOME`` / ``XDG_DATA_HOME`` / ``XDG_CACHE_HOME``
（Hyprland / Plasma / GNOME 都会导出）。Qt 与 platformdirs **优先读 XDG_***，
只有这些变量缺失时才回落到 ``$HOME``。所以真机验收若只重定向 HOME：

- 配置文件写进 ``~/.config/typetype/config.json``
- 打字历史 / 字频库写进 ``~/.local/share/typetype/*``

也就是说：跑一次"真机验收"，用户的真实成绩就被污染一次。**必须显式把四个
XDG 目录全部指进临时 HOME**。

## QML 磁盘缓存

默认开启时 Qt 会把编译产物写进 ``$XDG_CACHE_HOME/<argv0>/qmlcache``（一次
运行约 57 个文件），既拖慢又可能让陈旧缓存掩盖真实的 QML 编译错误。验收
场景追求确定性，一律 ``QML_DISABLE_DISK_CACHE=1``。

sandbox 约定：环境变量 ``UI_PROBE_HOME`` 标记当前进程已经处于隔离沙箱——
子进程（或父进程已经隔离好的场景 runner）据此复用同一个 HOME，避免俄罗斯
套娃式地反复创建临时目录。
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

#: 沙箱标记：值为隔离 HOME 的绝对路径
HOME_ENV = "UI_PROBE_HOME"

#: 临时 HOME 目录前缀（放 ~/ 下，不用 /tmp——真机启动会往 HOME 里拷几 MB 字体）
HOME_PREFIX = "ui-probe-home-"

_XDG_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
)

#: 本进程自己创建的沙箱 HOME（需要本进程负责清理）
_OWN: set[Path] = set()
_ATEXIT_READY = False


def _ensure_atexit() -> None:
    """注册一次退出清理：真机运行会在 HOME 里播种资源/字体，不清理就是残留。"""
    global _ATEXIT_READY
    if _ATEXIT_READY:
        return
    atexit.register(dispose_owned_homes)
    _ATEXIT_READY = True


def create_isolated_home(base: Path | None = None) -> Path:
    """在 ~/ 下创建一次性的隔离 HOME（不适合放 /tmp：容量小、字体拷贝会撑爆）。"""
    root = Path(base) if base is not None else Path.home()
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=HOME_PREFIX, dir=str(root)))


def apply_env_overrides(env: dict, home: Path) -> dict:
    """把 env（就地）改写成指向隔离 HOME 的运行环境。"""
    home = Path(home)
    env["HOME"] = str(home)
    env[HOME_ENV] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_STATE_HOME"] = str(home / ".local" / "state")
    env["QML_DISABLE_DISK_CACHE"] = "1"
    return env


def isolated_env(home: Path) -> dict:
    """复制当前进程环境并改写到隔离 HOME（给子进程用，不动自己进程）。"""
    return apply_env_overrides(dict(os.environ), home)


def enter_sandbox(base: Path | None = None) -> Path:
    """让**当前进程**进入隔离沙箱，返回 HOME 路径（幂等）。

    必须在 import / bootstrap 之前调用：路径一旦被 platformdirs 解析就晚了。
    已在沙箱内（``UI_PROBE_HOME`` 有效）时直接复用——那表示**调用方**持有它的
    生命周期，由调用方负责删除，本过程不越权清理（否则父还会用就被删了）。
    自己创建的则登记到 ``_OWNED``，进程退出前清理干净。
    """
    existing = os.environ.get(HOME_ENV)
    if existing and Path(existing).is_dir():
        return Path(existing)
    home = create_isolated_home(base)
    apply_env_overrides(os.environ, home)
    _OWN.add(home)
    _ensure_atexit()
    return home


def dispose_owned_homes() -> int:
    """删除本进程自己创建的沙箱 HOME，返回删除个数。"""
    removed = 0
    while _OWN:
        home = _OWN.pop()
        shutil.rmtree(home, ignore_errors=True)
        removed += 1
    return removed
