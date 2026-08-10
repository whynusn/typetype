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

import contextlib
import errno
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import types
from typing import Any
import traceback
from urllib.parse import urlparse


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

# Landlock 放行的最小 /etc 文件集（DNS/名称解析）：getaddrinfo 依赖
# nsswitch.conf 决定解析顺序、resolv.conf 提供 DNS 服务器、hosts 提供
# 静态映射。按文件授予而非整个 /etc，避免用户配置等敏感文件可读。
_ETC_DNS_FILES = (
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
)


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
    脚本所在目录（读+写，写入仍受 RLIMIT_FSIZE 约束）、/dev（urandom 等）、
    以及 DNS/名称解析所需的最小 /etc 文件集（_ETC_DNS_FILES）。其余路径
    全部拒绝 —— 用户配置、数据库、token 存储等敏感文件不可达。

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
        # DNS/名称解析的最小 /etc 文件集。Landlock path_beneath 规则对
        # 目录用目录 fd、对文件用文件 fd：文件须 os.open(path, os.O_RDONLY)
        # （不带 O_DIRECTORY）后把该 fd 作为 parent_fd 传入，规则即限定到
        # 单个文件，只授 READ_FILE。缺失文件（如无 resolv.conf 的系统）
        # 静默跳过。
        for etc_file in _ETC_DNS_FILES:
            try:
                file_fd = os.open(etc_file, os.O_RDONLY)
            except OSError:
                continue
            try:
                _landlock_add_rule(ruleset_fd, _LANDLOCK_FS_READ_FILE, file_fd)
            finally:
                os.close(file_fd)
        _landlock_set_no_new_privs()
        _landlock_restrict_self(ruleset_fd)
    except OSError:
        pass
    finally:
        try:
            os.close(ruleset_fd)
        except OSError:
            pass


# ── seccomp 系统调用过滤（最后防线之二）───────────────────────────────────
# 与 Landlock 同模式：ctypes 直调 prctl/原生 struct，Linux-only，不可用时
# 静默降级。目的不是通用限制（文件系统归 Landlock、内存/CPU/进程数归
# rlimits、网络归白名单模块），而是封锁「内核级逃逸原语」—— 即使脚本在
# Python 层逃逸（拿到真实 open 等），也拿不到 ptrace 附加、命名空间创建、
# 模块加载、重启/kexec 等原始系统调用。只安装到沙箱子进程，绝不安装到
# 主 typetype 进程。
#
# 注意：seccomp_data 布局为 { int nr; __u32 arch; ... } —— nr 在 offset 0、
# arch 在 offset 4（与任务书描述相反；offset 写反过滤器将永不该杀）。

_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2
_SECCOMP_RET_ALLOW = 0x7FFF0000
_SECCOMP_RET_KILL_PROCESS = 0x80000000  # 内核 4.14+，整进程击杀（含所有线程）
_SECCOMP_RET_KILL_THREAD = 0x00000000  # 老内核的 SECCOMP_RET_KILL

# classic BPF 指令码：BPF_LD|BPF_W|BPF_ABS、BPF_JMP|BPF_JEQ|BPF_K、BPF_RET|BPF_K
_BPF_LD_W_ABS = 0x20
_BPF_JMP_JEQ_K = 0x15
_BPF_RET_K = 0x06

# AUDIT_ARCH_*（__AUDIT_ARCH_LE=0x40000000 | __AUDIT_ARCH_64BIT=0x80000000 | EM_*）
_AUDIT_ARCH_X86_64 = 0xC000003E
_AUDIT_ARCH_I386 = 0x40000003
_AUDIT_ARCH_AARCH64 = 0xC00000B7

# 内核级逃逸原语封锁清单：每条 = 一类逃逸（ptrace 附加读写任意进程内存、
# 命名空间创建/加入、文件系统/根目录切换、内核模块加载、重启/kexec、
# BPF 特权操作、用户态页面错误劫持、IO 端口特权等）。刻意不封锁
# socket/connect/open/read/write/execve/clone/fork —— 脚本合法网络（httpx）
# 与文件 IO（Landlock 限制内）依赖它们，封锁会误杀正常脚本。
# 数值来自本机 asm/unistd_*.h 与 asm-generic/unistd.h；x86_64 为精确值
# （开发机），i386/aarch64 best-effort（值同样取自同源内核头文件）。
_DENY_ESCAPES: dict[str, dict[int, str]] = {
    "x86_64": {
        101: "ptrace — 附加调试器，读写任意进程内存",
        165: "mount — 挂载文件系统",
        166: "umount2 — 卸载文件系统",
        155: "pivot_root — 切换根文件系统",
        161: "chroot — 逃逸目录 jail",
        169: "reboot — 重启机器",
        246: "kexec_load — 加载新内核",
        320: "kexec_file_load — 从文件加载新内核",
        321: "bpf — 加载 BPF 程序/特权操作",
        323: "userfaultfd — 用户态页面错误劫持",
        298: "perf_event_open — 内核事件探测",
        167: "swapon — 启用交换设备",
        168: "swapoff — 禁用交换设备",
        170: "sethostname — 修改主机名",
        308: "setns — 加入其它命名空间",
        272: "unshare — 创建/脱离命名空间",
        175: "init_module — 加载内核模块",
        313: "finit_module — 从 fd 加载内核模块",
        176: "delete_module — 卸载内核模块",
        172: "iopl — IO 特权级",
        173: "ioperm — IO 端口权限",
        310: "process_vm_readv — 读其它进程内存",
        311: "process_vm_writev — 写其它进程内存",
        312: "kcmp — 进程比较/侧信道",
    },
    "i386": {
        26: "ptrace",
        21: "mount",
        52: "umount2",
        217: "pivot_root",
        61: "chroot",
        88: "reboot",
        283: "kexec_load",
        336: "perf_event_open",
        87: "swapon",
        115: "swapoff",
        74: "sethostname",
        346: "setns",
        310: "unshare",
        128: "init_module",
        350: "finit_module",
        129: "delete_module",
        110: "iopl",
        101: "ioperm",
        347: "process_vm_readv",
        348: "process_vm_writev",
        349: "kcmp",
    },
    "aarch64": {
        117: "ptrace",
        40: "mount",
        39: "umount2",
        41: "pivot_root",
        51: "chroot",
        142: "reboot",
        104: "kexec_load",
        280: "bpf",
        282: "userfaultfd",
        241: "perf_event_open",
        224: "swapon",
        225: "swapoff",
        161: "sethostname",
        268: "setns",
        97: "unshare",
        105: "init_module",
        273: "finit_module",
        106: "delete_module",
        270: "process_vm_readv",
        271: "process_vm_writev",
        272: "kcmp",
    },
}

_ARCH_CONSTANTS = {
    "x86_64": _AUDIT_ARCH_X86_64,
    "i386": _AUDIT_ARCH_I386,
    "aarch64": _AUDIT_ARCH_AARCH64,
}

# 探测子进程源码：设置 no_new_privs 后安装一个 allow-everything 平凡过滤器，
# 成功打印 sentinel。自包含（不 import runner），供 subprocess.run(-c) 执行。
_SECCOMP_PROBE = r"""import ctypes, sys
libc = ctypes.CDLL(None, use_errno=True)
libc.prctl.restype = ctypes.c_int
libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
class SockFilter(ctypes.Structure):
    _fields_ = [('code', ctypes.c_uint16), ('jt', ctypes.c_uint8), ('jf', ctypes.c_uint8), ('k', ctypes.c_uint32)]
class SockFprog(ctypes.Structure):
    _fields_ = [('len', ctypes.c_uint16), ('filter', ctypes.POINTER(SockFilter))]
allow = SockFilter(0x06, 0, 0, 0x7fff0000)  # BPF_RET | BPF_K, SECCOMP_RET_ALLOW
prog = SockFprog(1, ctypes.pointer(allow))
# PR_SET_NO_NEW_PRIVS=38：无 CAP_SYS_ADMIN 时安装过滤器的前置条件
if libc.prctl(38, 1, 0, 0, 0) != 0:
    sys.exit(1)
# PR_SET_SECCOMP=22, SECCOMP_MODE_FILTER=2
ok = libc.prctl(22, 2, ctypes.cast(ctypes.pointer(prog), ctypes.c_void_p), 0, 0) == 0
print('SECKPROBE:OK' if ok else 'SECKPROBE:FAIL')
sys.exit(0 if ok else 1)
"""

_seccomp_available_cache: bool | None = None


def seccomp_available() -> bool:
    """seccomp filter 是否可用的探测（供测试与降级判定共用）。

    绝不安装过滤器到本进程 —— 探测在独立子进程中完成：子进程设置
    no_new_privs 后安装 allow-everything 平凡过滤器，成功即认为可用。
    结果缓存，避免每次沙箱运行都重复启动探测子进程。
    """
    global _seccomp_available_cache
    if _seccomp_available_cache is not None:
        return _seccomp_available_cache
    if not sys.platform.startswith("linux"):
        _seccomp_available_cache = False
        return False
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _SECCOMP_PROBE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        _seccomp_available_cache = False
        return False
    _seccomp_available_cache = proc.returncode == 0 and "SECKPROBE:OK" in (
        proc.stdout or ""
    )
    return _seccomp_available_cache


def _seccomp_arch_key() -> str:
    """当前机器架构 → deny 表键（'' = 无匹配表，跳过 seccomp）。"""
    import platform

    machine = platform.machine()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("i386", "i486", "i586", "i686"):
        return "i386"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return ""


def _expected_arch() -> int:
    return _ARCH_CONSTANTS.get(_seccomp_arch_key(), 0)


def _build_seccomp_filter(
    expected_arch: int,
    deny: dict[int, str],
    kill_ret: int = _SECCOMP_RET_KILL_PROCESS,
) -> list[tuple[int, int, int, int]]:
    """构造 seccomp BPF 程序，返回 (code, jt, jf, k) 元组列表（即 sock_filter）。

    布局：
      LD arch(off 4) → JEQ 期望架构 → 不匹配 RET ALLOW（i386 compat / x32
      等未知架构放行 —— 这些 ABI 的逃逸原语 syscall 号不同，宁放过不错杀，
      脚本也无法轻易切换到 32 位 ABI 执行）
      LD syscall_nr(off 0) → 逐条 JEQ deny → 命中 RET KILL；不命中继续
      末尾 RET ALLOW（默认放行，脚本合法网络/文件 IO 不受影响）
    """
    prog: list[tuple[int, int, int, int]] = [
        (_BPF_LD_W_ABS, 0, 0, 4),  # seccomp_data.arch
        (_BPF_JMP_JEQ_K, 1, 0, expected_arch),
        (_BPF_RET_K, 0, 0, _SECCOMP_RET_ALLOW),
        (_BPF_LD_W_ABS, 0, 0, 0),  # seccomp_data.nr
    ]
    for nr in sorted(deny):
        prog.append((_BPF_JMP_JEQ_K, 0, 1, nr))
        prog.append((_BPF_RET_K, 0, 0, kill_ret))
    prog.append((_BPF_RET_K, 0, 0, _SECCOMP_RET_ALLOW))
    return prog


def _apply_seccomp() -> None:
    """安装 seccomp BPF 过滤器，封锁内核级逃逸原语。

    与 Landlock 同模式：Linux-only、不可用时静默降级（保留 rlimits +
    Landlock 防线）。只在沙箱子进程内调用，绝不安装到主 typetype 进程。

    顺序：main() 先调 _apply_landlock 再调本函数；no_new_privs 在此幂等地
    再次设置（Landlock 已设置过；Landlock 不可用时此处补设），保证无
    CAP_SYS_ADMIN 的普通用户子进程也能安装过滤器。
    """
    if not sys.platform.startswith("linux"):
        return
    if not seccomp_available():
        sys.stderr.write(
            "[ott-script] seccomp 不可用，跳过（仅保留 rlimits + Landlock）\n"
        )
        return

    deny = _DENY_ESCAPES.get(_seccomp_arch_key())
    if not deny:
        return  # 未知架构无 deny 表，安装空过滤器无意义

    import ctypes

    class SockFilter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_uint16),
            ("jt", ctypes.c_uint8),
            ("jf", ctypes.c_uint8),
            ("k", ctypes.c_uint32),
        ]

    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(SockFilter))]

    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]

    # PR_SET_NO_NEW_PRIVS=38（幂等）
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        return

    def install(kill_ret: int) -> bool:
        prog = _build_seccomp_filter(_expected_arch(), deny, kill_ret)
        filters = (SockFilter * len(prog))(
            *(SockFilter(code, jt, jf, k) for code, jt, jf, k in prog)
        )
        sock_prog = SockFprog(len(prog), filters)
        # PR_SET_SECCOMP=22, SECCOMP_MODE_FILTER=2，arg3 = &sock_fprog
        return (
            libc.prctl(
                _PR_SET_SECCOMP,
                _SECCOMP_MODE_FILTER,
                ctypes.cast(ctypes.pointer(sock_prog), ctypes.c_void_p),
                0,
                0,
            )
            == 0
        )

    # KILL_PROCESS 内核 4.14+ 才识别；老内核 EINVAL 拒绝整条过滤器 →
    # 回退 KILL_THREAD(0)（原 SECCOMP_RET_KILL，单线程子进程等价整进程击杀）。
    if not install(_SECCOMP_RET_KILL_PROCESS):
        if ctypes.get_errno() != errno.EINVAL:
            return
        install(_SECCOMP_RET_KILL_THREAD)


# ── 受限 builtins ──────────────────────────────────────────────────────


def _build_safe_builtins() -> dict:
    """构建受限的 builtins 字典。

    说明：对象模型遍历（().__class__.__bases__[0].__subclasses__() → ...
    → __globals__ → open）是纯属性访问，不需要调用任何内置函数，本层无法
    在 builtins 层面拦截（type/object/getattr 等虽已禁用，但 `x.__class__`
    这类语法无需调用它们）。主防线是 AST 检查（ott_script_safety.py 的
    banned_object_model_access）；本层黑名单 + 子进程隔离（rlimits +
    Landlock）是兜底边界。不要全局 monkeypatch object 内部属性 ——
    bs4/Crypto 等白名单库依赖对象模型内部机制，全局修改既脆弱又可能
    破坏合法脚本。
    """
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


# ── 一次性凭据 fd 助手（ADR-011 Phase 5.4）─────────────────────────────


class _SandboxSecrets:
    """脚本凭据访问助手（注入脚本 globals）。

    凭据经父进程一次性 fd 继承（pass_fds）传入，脚本通过
    ``sandbox.get_secret(name)`` 读取一次后 fd 即关闭。值不落盘、
    不进环境变量，仅存在于子进程 fd 表 → 内存，父进程写端已关闭。
    """

    def __init__(self, fd_map: dict[str, int]) -> None:
        self._fd_map = dict(fd_map)

    def get_secret(self, name: str) -> str:
        """读取并返回指定凭据（一次性：读后 fd 关闭，再次读取报错）。"""
        fd = self._fd_map.pop(name, None)
        if fd is None:
            raise RuntimeError(f"脚本未声明凭据 {name!r}")
        try:
            chunks: list[bytes] = []
            while True:
                data = os.read(fd, 4096)
                if not data:
                    break
                chunks.append(data)
            return b"".join(chunks).decode("utf-8")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


def _parse_runner_config(raw: str) -> tuple[dict[str, int], list[str]]:
    """解析父进程经 stdin JSON 传入的配置（容错）。

    ``secrets``: {name: fd} 凭据映射（一次凭据 fd 继承）。
    ``network_allowlist``: permissions.network 域名白名单（缺省/畸形 → 空，
    空白名单 = 拒绝一切 http(s) 请求，脚本网络 deny-by-default）。
    """
    secrets: dict[str, int] = {}
    allowlist: list[str] = []
    if not raw.strip():
        return secrets, allowlist
    try:
        parsed = json.loads(raw)
    except ValueError:
        return secrets, allowlist
    if not isinstance(parsed, dict):
        return secrets, allowlist
    raw_secrets = parsed.get("secrets")
    if isinstance(raw_secrets, dict):
        for name, spec in raw_secrets.items():
            if (
                isinstance(name, str)
                and isinstance(spec, dict)
                and isinstance(spec.get("fd"), int)
            ):
                secrets[name] = spec["fd"]
    raw_network = parsed.get("network_allowlist")
    if isinstance(raw_network, list):
        allowlist = [h for h in raw_network if isinstance(h, str) and h.strip()]
    return secrets, allowlist


# ── 网络白名单门控（ADR-011 Phase 2.2 运行时强制）───────────────────────
# 脚本网络 deny-by-default：manifest 声明 permissions.network 才允许对应
# 域名；未声明 → 空白名单 → 一切 http(s) 请求被拒。门控分两层：
#   1) httpx 模块替身 —— 拦截全部网络入口（模块级函数 + Client），
#      URL 未命中白名单即抛 _NetworkDeniedError；
#   2) DNS pin —— 覆盖 getaddrinfo 解析路径，白名单域名解析出私网/
#      环回/链路本地等内网地址时剔除该结果（防 rebinding 到内网 SSRF）。


class _NetworkDeniedError(RuntimeError):
    """请求被网络白名单拒绝。"""


def _is_private_ip(ip: str) -> bool:
    """保守判定：私网/环回/链路本地/组播/保留/未指定地址一律视为内网。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # 非合法 IP → 保守拒绝
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        # IPv4-mapped IPv6（::ffff:10.0.0.1）在部分 Python 版本下 is_private
        # 判定为 False，显式解包为 IPv4 再判定（与 ott_rule_interpreter 一致）。
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _normalize_allow_entry(entry: str) -> str:
    """归一化白名单条目：允许裸域名或完整 URL（取 host），去尾点转小写。"""
    host = entry.strip().lower().rstrip(".")
    if "://" in host:
        host = (urlparse(host).hostname or "").lower().rstrip(".")
    return host


def _is_domain_allow_entry(host: str) -> bool:
    """白名单只接受域名形式：≥2 段、非 IP 字面量/CIDR。

    拒绝 TLD-only（``com``）与 IP 条目（``127.0.0.1`` / ``0.0.0.0/0`` /
    IPv6），否则超宽条目等于近乎完全网络访问。
    """
    if not host or len(host.split(".")) < 2:
        return False
    try:
        ipaddress.ip_network(host, strict=False)
    except ValueError:
        return True
    return False


class _NetworkGate:
    """脚本网络白名单门控。

    - 空白名单 → 拒绝一切 http(s)（脚本无 manifest 声明 = 无网络）；
    - 子域匹配：``example.com`` 允许 ``api.example.com``；
    - 仅放行 http/https scheme。
    """

    def __init__(self, allowlist: list[str] | None = None) -> None:
        self._entries: list[str] = []
        for entry in allowlist or []:
            if not isinstance(entry, str):
                continue
            host = _normalize_allow_entry(entry)
            # TLD-only / IP 字面量等超宽或非域名条目不入白名单（等价丢弃）
            if host and _is_domain_allow_entry(host):
                self._entries.append(host)

    def allows(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or not self._entries:
            return False
        return any(
            host == entry or host.endswith("." + entry) for entry in self._entries
        )

    def check(self, url: str) -> None:
        if not self.allows(url):
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            _audit_network_denied(host, url)
            raise _NetworkDeniedError(f"主机不在网络白名单内: {host}")


def _audit_network_denied(host: str, url: str) -> None:
    """拒绝请求时写一条审计行到 stderr。

    只记录 host、URL 长度与 URL 的 sha256 前 16 hex —— 不落完整 URL，
    防 query string 等敏感信息随日志泄漏。审计在抛错前执行，脚本
    except 捕获后也无法掩盖拒绝事实。
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    sys.stderr.write(
        f"[ott-script-audit] blocked host={host} "
        f"url_len={len(url)} url_sha256_prefix={digest}\n"
    )
    sys.stderr.flush()


def _make_pinned_getaddrinfo(original):
    """构造 DNS pin 包装的 getaddrinfo（可单测；原函数即真实 socket.getaddrinfo）。

    过滤解析结果：解析出内网地址（私网/环回/链路本地等）的条目剔除，
    全部被剔除 → 返回空列表（连接自然失败）。脚本无法 import socket，
    此包装只影响沙箱内部 httpx/httpcore 的解析路径。
    """

    def _pinned(host, port, family=0, type=0, proto=0, flags=0):
        results = original(host, port, family, type, proto, flags)
        kept = [r for r in results if not _is_private_ip(r[4][0] if r[4] else "")]
        return kept if kept else []

    return _pinned


def _install_dns_pin() -> None:
    """安装 DNS pin（仅白名单生效时调用；空列表无网络，pin 无意义）。"""
    import socket

    socket.getaddrinfo = _make_pinned_getaddrinfo(socket.getaddrinfo)


# httpx 模块级函数与构造参数拆分：verify/cert/proxy/trust_env 是 Client
# 构造参数（httpx._api 把它们传给 Client()），其余（headers/params/json/
# timeout 等）是请求参数。代理类参数一律拒绝（沙箱禁止自定义代理/挂载）。
_CTOR_ONLY_KWARGS = ("verify", "cert", "proxy", "trust_env")
_MODULE_HTTPX_FNS = ("get", "post", "put", "patch", "delete", "head", "options")
_OVERRIDDEN_HTTPX_NAMES = frozenset(
    {
        "Client",
        "AsyncClient",
        "request",
        "stream",
        # transport 构造器不暴露：脚本可伪造 MockTransport/自建 transport
        # 绕过 gate（transport 层不走 Client.send），属不必要攻击面
        "HTTPTransport",
        "AsyncHTTPTransport",
        "MockTransport",
        "ASGITransport",
        "WSGITransport",
        "BaseTransport",
        "AsyncBaseTransport",
        *_MODULE_HTTPX_FNS,
    }
)


def _make_gated_client_cls(gate: _NetworkGate):
    """构造受门控的 httpx.Client 子类（每次调用闭包构造，共享 gate）。"""
    import httpx as real_httpx

    class _GatedClient(real_httpx.Client):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("proxy") is not None or kwargs.get("mounts") is not None:
                raise ValueError("沙箱禁止自定义代理/挂载")
            # 无条件禁用环境代理读取（脚本传 trust_env=True 也无法覆盖）：
            # 防止代理侧信道绕过网络白名单
            kwargs["trust_env"] = False
            super().__init__(*args, **kwargs)
            self._sandbox_gate = gate

        def send(
            self, request: real_httpx.Request, **kwargs: Any
        ) -> real_httpx.Response:
            gate.check(str(request.url))
            # 重定向递归（_send_handling_redirects → self.send）同样经过本
            # 覆盖点，每个跳转 hop 都重新校验 Location URL。
            return super().send(request, **kwargs)

    return _GatedClient


def _make_module_fn(gate: _NetworkGate, name: str, client_cls):
    """模块级 get/post/... 包装：每次调用新建门控 Client（镜像 httpx._api）。"""

    def _fn(url, *args: Any, **kwargs: Any):
        ctor_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _CTOR_ONLY_KWARGS}
        with client_cls(**ctor_kwargs) as client:
            return getattr(client, name)(url, *args, **kwargs)

    _fn.__name__ = name
    return _fn


def _make_request_fn(gate: _NetworkGate, client_cls):
    def _request(method, url, *args: Any, **kwargs: Any):
        ctor_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _CTOR_ONLY_KWARGS}
        with client_cls(**ctor_kwargs) as client:
            return client.request(method, url, *args, **kwargs)

    _request.__name__ = "request"
    return _request


def _make_stream_fn(gate: _NetworkGate, client_cls):
    """模块级 stream：Client 生命周期需覆盖整个流式上下文（生成器延迟求值）。"""

    @contextlib.contextmanager
    def _stream(method, url, *args: Any, **kwargs: Any):
        ctor_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _CTOR_ONLY_KWARGS}
        client = client_cls(**ctor_kwargs)
        try:
            with client.stream(method, url, *args, **kwargs) as response:
                yield response
        finally:
            client.close()

    _stream.__name__ = "stream"
    return _stream


def _build_httpx_wrapper(gate: _NetworkGate) -> types.ModuleType:
    """构建受门控的 httpx 模块替身。

    放入 sys.modules["httpx"] 拦截 ``import httpx`` / ``from httpx import X``：
    - 复制真实 httpx 的只读属性（异常类、Timeout、codes、URL 等），脚本
      ``except httpx.HTTPError`` 等仍可工作；
    - 覆盖全部网络入口：Client（构造即持门控）与模块级函数；
    - 刻意不暴露 AsyncClient（异步不在沙箱支持面内，缺省即 AttributeError）。
    """
    import httpx as real_httpx

    proxy = types.ModuleType("httpx")
    proxy.__doc__ = "沙箱门控 httpx（仅同步；网络受白名单限制）"
    for name in dir(real_httpx):
        if name in _OVERRIDDEN_HTTPX_NAMES:
            continue
        setattr(proxy, name, getattr(real_httpx, name))
    client_cls = _make_gated_client_cls(gate)
    proxy.Client = client_cls
    for name in _MODULE_HTTPX_FNS:
        setattr(proxy, name, _make_module_fn(gate, name, client_cls))
    proxy.request = _make_request_fn(gate, client_cls)
    proxy.stream = _make_stream_fn(gate, client_cls)
    return proxy


# ── 主逻辑 ────────────────────────────────────────────────────────────


def run_script(
    script_path: str,
    secrets: dict[str, int] | None = None,
    network_allowlist: list[str] | None = None,
) -> list:
    """在受限环境中执行脚本并返回 fetch_entries() 的结果。

    secrets: 可选的 {凭据名: fd} 映射（父进程声明后注入）。仅当
    映射非空时才向脚本 globals 注入 ``sandbox`` 助手 —— 脚本无法
    自行请求任意凭据，只有 manifest 声明过的名字可读。

    network_allowlist: manifest 声明的 permissions.network 域名白名单。
    空/None → 拒绝一切 http(s) 请求（deny-by-default）；非空 → 同时
    安装 DNS pin（防白名单域名 rebinding 到内网）。

    双沙箱（Landlock + seccomp）均不可用时拒绝执行：此时防御仅剩
    rlimits + AST 检查，不足以对抗逃逸，宁拒不降级（单侧可用照常执行）。
    """
    if not landlock_available() and not seccomp_available():
        sys.stderr.write(
            "[ott-script] Landlock 与 seccomp 均不可用，拒绝执行 L3 脚本\n"
        )
        raise RuntimeError("Landlock 与 seccomp 均不可用，拒绝执行 L3 脚本")
    gate = _NetworkGate(network_allowlist)
    if gate._entries:
        _install_dns_pin()

    # 构建受限 globals
    safe_globals: dict = {
        "__builtins__": _build_safe_builtins(),
        "__name__": "__ott_script__",
        "__file__": script_path,
    }

    if secrets:
        safe_globals["sandbox"] = _SandboxSecrets(secrets)

    # 预导入白名单模块
    for mod_name in sorted(ALLOWED_MODULES):
        if mod_name in ("builtins",):
            continue
        mod = _import_allowed_module(mod_name)
        if mod is not None:
            root = mod_name.split(".", maxsplit=1)[0]
            safe_globals[root] = mod

    # 用门控替身替换真实 httpx：拦截脚本的一切 httpx 访问（import/from/别名）
    sys.modules["httpx"] = _build_httpx_wrapper(gate)
    safe_globals["httpx"] = sys.modules["httpx"]

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
    # Windows 下子进程 stdout/stderr 默认继承 locale 编码（cp1252），
    # ensure_ascii=False 输出中文 JSON 会 UnicodeEncodeError，强制 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    if len(argv) < 2:
        print("用法: python ott_script_runner.py <script_path>", file=sys.stderr)
        return 1

    script_path = argv[1]
    if not os.path.isfile(script_path):
        print(f"脚本不存在: {script_path}", file=sys.stderr)
        return 1

    # 可选配置：父进程经 stdin JSON 传入（TTY 手动运行时不读）
    secrets: dict[str, int] = {}
    allowlist: list[str] = []
    if not sys.stdin.isatty():
        secrets, allowlist = _parse_runner_config(sys.stdin.read())

    try:
        _set_resource_limits()
        # httpx 及其 zlib/ssl 依赖必须在 Landlock 限制文件系统前加载，
        # 否则系统 Python 从 /lib 读取 libz.so.1 / libssl 会被拒绝。
        import httpx  # noqa: F401

        _apply_landlock(os.path.dirname(os.path.abspath(script_path)))
        entries = run_script(script_path, secrets or None, allowlist)
        # 序列化结果到 stdout
        json.dump(entries, sys.stdout, ensure_ascii=False, default=str)
        sys.stdout.flush()
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
