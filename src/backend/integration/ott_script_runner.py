"""ott-script 子进程沙箱入口。

由 ScriptSandbox 通过 subprocess.run() 启动，在独立 Python 进程内执行
用户脚本。资源限制（内存/CPU/proc 数）在导入任何模块之前设置，确保
恶意脚本无法绕过。

用法：
    python ott_script_runner.py <script_path>

退出码：
    0 — 成功，stdout 为 fetch_entries() 结果的 JSON
    1 — 执行失败，stderr 为错误信息
    非零 — 资源限制触发（SIGXCPU / SIGKILL 等）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
import traceback


# ── 资源限制（必须在导入任何第三方模块之前设置）──────────────────────────


def _set_resource_limits() -> None:
    """设置子进程资源限制。失败不退出（可能在不受支持的平台）。"""
    try:
        import resource
    except ImportError:
        return  # Windows 无 resource 模块

    # 内存：软 256MB，硬 512MB
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (256 * 1024 * 1024, 512 * 1024 * 1024),
        )
    except (ValueError, OSError):
        pass

    # CPU 时间：软 30s，硬 35s
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (30, 35))
    except (ValueError, OSError):
        pass

    # 禁止创建新进程
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except (ValueError, OSError):
        pass

    # 禁止写入超大文件（10MB）
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    except (ValueError, OSError):
        pass


# ── Landlock 文件系统隔离（最后防线）──────────────────────────────────────
# os.landlock_* 在部分 Python 构建（uv standalone 等）缺失，统一经 ctypes
# 直调 syscall。landlock_ruleset_attr 的 ksize_min 自 5.13 起恒为 8 字节，
# 新内核自动补零扩展 —— 固定传 size=8 兼容所有 5.13+ 内核。

_LANDLOCK_SYS_CREATE = 444
_LANDLOCK_SYS_ADD_RULE = 445
_LANDLOCK_SYS_RESTRICT = 446
_LANDLOCK_RULE_PATH_BENEATH = 1

_LANDLOCK_FS_EXECUTE = 1 << 0
_LANDLOCK_FS_WRITE_FILE = 1 << 1
_LANDLOCK_FS_READ_FILE = 1 << 2
_LANDLOCK_FS_READ_DIR = 1 << 3
_LANDLOCK_FS_MAKE_REG = 1 << 8


def _landlock_syscall(*argtypes: Any) -> Any:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.syscall.argtypes = list(argtypes)
    return libc.syscall


def _landlock_create(handled_access_fs: int) -> int:
    import ctypes

    syscall = _landlock_syscall(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32
    )
    attr = ctypes.create_string_buffer(handled_access_fs.to_bytes(8, "little"), 8)
    fd = syscall(_LANDLOCK_SYS_CREATE, ctypes.byref(attr), 8, 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    return fd


def _landlock_add_rule(ruleset_fd: int, allowed_access: int, parent_fd: int) -> None:
    import ctypes

    class PathBeneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    syscall = _landlock_syscall(
        ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
    )
    rule = PathBeneath(allowed_access, parent_fd)
    if (
        syscall(
            _LANDLOCK_SYS_ADD_RULE,
            ruleset_fd,
            _LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(rule),
            0,
        )
        != 0
    ):
        raise OSError(ctypes.get_errno(), "landlock_add_rule")


def _landlock_restrict_self(ruleset_fd: int) -> None:
    import ctypes

    syscall = _landlock_syscall(ctypes.c_long, ctypes.c_int, ctypes.c_uint32)
    if syscall(_LANDLOCK_SYS_RESTRICT, ruleset_fd, 0) != 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")


def _landlock_set_no_new_privs() -> None:
    # 内核要求 landlock_restrict_self 前具备 no_new_privs 或 CAP_SYS_ADMIN，
    # 普通用户子进程只能走前者。PR_SET_NO_NEW_PRIVS = 38。
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS)")


def landlock_available() -> bool:
    """Landlock 是否可用的探测（供测试与降级判定共用）。"""
    try:
        # handled=0 会触发内核 ENOMSG（空 access），必须用有效位探测
        ruleset_fd = _landlock_create(_LANDLOCK_FS_READ_FILE)
    except (OSError, AttributeError, TypeError):
        return False
    os.close(ruleset_fd)
    return True


def _apply_landlock(script_dir: str) -> None:
    """限制子进程文件系统访问，阻断对象模型逃逸读取任意文件。

    放行：Python 运行时（sys.prefix / sys.base_prefix，含 site-packages）、
    脚本所在目录（读+写，写入仍受 RLIMIT_FSIZE 约束）、/etc（DNS 解析）、
    /dev（urandom 等）。其余路径全部拒绝 —— 用户配置、数据库、token
    存储等敏感文件不可达。

    内核 < 5.13 或非 Linux 时静默降级（保留 rlimits 防线）。
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        ruleset_fd = _landlock_create(
            _LANDLOCK_FS_EXECUTE
            | _LANDLOCK_FS_READ_FILE
            | _LANDLOCK_FS_READ_DIR
            | _LANDLOCK_FS_WRITE_FILE
            | _LANDLOCK_FS_MAKE_REG
        )
    except (OSError, AttributeError):
        return

    read_access = _LANDLOCK_FS_READ_FILE | _LANDLOCK_FS_READ_DIR | _LANDLOCK_FS_EXECUTE
    write_access = _LANDLOCK_FS_WRITE_FILE | _LANDLOCK_FS_MAKE_REG
    paths: dict[str, int] = {
        sys.prefix: read_access,
        sys.base_prefix: read_access,
        script_dir: read_access | write_access,
        "/etc": read_access,
        "/dev": read_access,
    }

    try:
        for path, access in paths.items():
            try:
                parent_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            except OSError:
                continue
            try:
                _landlock_add_rule(ruleset_fd, access, parent_fd)
            finally:
                os.close(parent_fd)
        _landlock_set_no_new_privs()
        _landlock_restrict_self(ruleset_fd)
    except OSError:
        pass
    finally:
        try:
            os.close(ruleset_fd)
        except OSError:
            pass


# ── 受限 builtins ──────────────────────────────────────────────────────


def _build_safe_builtins() -> dict:
    """构建受限的 builtins 字典。"""
    import builtins as _builtins

    banned = {
        "eval",
        "exec",
        "compile",
        "open",
        "exit",
        "quit",
        "help",
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "type",
        "object",
        "__build_class__",
        "memoryview",
        "bytearray",
    }
    safe: dict = {}
    for name in dir(_builtins):
        if name in banned:
            continue
        obj = getattr(_builtins, name)
        if name == "print":
            safe[name] = _safe_print
            continue
        safe[name] = obj
    # 提供受限的 __import__，仅放行白名单模块
    safe["__import__"] = _make_safe_import()
    return safe


def _make_safe_import():
    """创建一个受限的 __import__，仅允许白名单模块。"""

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if not any(
            name == allowed or name.startswith(allowed + ".")
            for allowed in ALLOWED_MODULES
        ):
            raise ImportError(f"模块 {name!r} 不在沙箱白名单中")
        return __import__(name, globals, locals, fromlist, level)

    return _safe_import


def _safe_print(*args, **kwargs) -> None:
    """沙箱内的 print 重定向到 stderr（不污染 stdout JSON）。"""
    msg = " ".join(str(a) for a in args)
    try:
        sys.stderr.write(f"[ott-script] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ── 白名单模块 ────────────────────────────────────────────────────────

ALLOWED_MODULES = frozenset(
    {
        "json",
        "re",
        "time",
        "datetime",
        "hashlib",
        "base64",
        "urllib.parse",
        "http",
        "email",
        "collections",
        "itertools",
        "functools",
        "math",
        "random",
        "string",
        "textwrap",
        "unicodedata",
        "httpx",
        "Crypto",
        "Crypto.Cipher",
        "Crypto.Util",
        "Crypto.Util.Padding",
        "bs4",
    }
)


def _import_allowed_module(mod_name: str):
    """导入白名单模块，返回模块对象或 None。"""
    if not any(
        mod_name == allowed or mod_name.startswith(allowed + ".")
        for allowed in ALLOWED_MODULES
    ):
        return None
    try:
        parts = mod_name.split(".")
        mod = __import__(mod_name, fromlist=[parts[-1]])
        return mod
    except ImportError:
        return None


# ── 主逻辑 ────────────────────────────────────────────────────────────


def run_script(script_path: str) -> list:
    """在受限环境中执行脚本并返回 fetch_entries() 的结果。"""
    # 构建受限 globals
    safe_globals: dict = {
        "__builtins__": _build_safe_builtins(),
        "__name__": "__ott_script__",
        "__file__": script_path,
    }

    # 预导入白名单模块
    for mod_name in sorted(ALLOWED_MODULES):
        if mod_name in ("builtins",):
            continue
        mod = _import_allowed_module(mod_name)
        if mod is not None:
            root = mod_name.split(".", maxsplit=1)[0]
            safe_globals[root] = mod

    # 读取脚本源码
    try:
        with open(script_path, encoding="utf-8") as f:
            source = f.read(256 * 1024)  # 256KB 上限
    except OSError as e:
        raise RuntimeError(f"无法读取脚本: {e}") from e

    # 编译 + 执行
    try:
        code = compile(source, filename=f"<ott-script:{script_path}>", mode="exec")
    except SyntaxError as e:
        raise RuntimeError(f"脚本语法错误: {e}") from e

    exec(code, safe_globals)

    # 调用 fetch_entries()
    fetch_fn = safe_globals.get("fetch_entries")
    if not callable(fetch_fn):
        raise RuntimeError("脚本未定义 fetch_entries() 函数")

    result = fetch_fn()
    if not isinstance(result, list):
        raise RuntimeError("fetch_entries() 必须返回列表")

    return result


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python ott_script_runner.py <script_path>", file=sys.stderr)
        return 1

    script_path = argv[1]
    if not os.path.isfile(script_path):
        print(f"脚本不存在: {script_path}", file=sys.stderr)
        return 1

    try:
        _set_resource_limits()
        _apply_landlock(os.path.dirname(os.path.abspath(script_path)))
        entries = run_script(script_path)
        # 序列化结果到 stdout
        json.dump(entries, sys.stdout, ensure_ascii=False, default=str)
        sys.stdout.flush()
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
