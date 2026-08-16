"""OTT Repo ott-script 下载、缓存、沙箱执行。

脚本必须定义 fetch_entries() -> list[dict]，返回标准化 entry 列表。
沙箱限制：
- 仅允许白名单模块（httpx/json/Crypto/bs4 等）
- 在独立 Python 子进程中执行（subprocess.run + 资源限制）
- 子进程资源限制：256MB 内存 / 30s CPU / 禁止 fork / 10MB 文件写入
- AST 安全检查作为第一道关卡（拦截明显恶意，减少子进程启动开销）
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ..utils.logger import log_warning
from .ott_normalization import (
    _script_authority,
    normalize_summary,
    redact_url,
    to_jsdelivr_url,
)
from .ott_rule_interpreter import CLIENT_API_LEVEL
from .ott_script_safety import validate_script_source

if TYPE_CHECKING:
    from ..ports.token_store import TokenStore
    from .smart_router import SmartRouteSelector

# ── 常量 ────────────────────────────────────────────────────────────────

# CGNAT 共享地址空间（RFC 6598，100.64.0.0/10），不在 ipaddress.is_private
# 覆盖内；与 ott_rule_interpreter 的 URL 拦截策略对齐，显式拦截。
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

SCRIPT_MAX_BYTES = 256 * 1024  # 256 KB
SCRIPT_EXEC_TIMEOUT_S = 30.0
MAX_ENTRIES_PER_SCRIPT = 1000
# 一次性管道（os.pipe）缓冲上限：写入值须一次写完且不被父进程阻塞
PIPE_SECRET_MAX_BYTES = 64 * 1024
# 子进程 stdout JSON 上限：超出即拒绝（防子进程输出撑爆主进程内存）
STDOUT_MAX_BYTES = 10 * 1024 * 1024
# 单条 entry content 上限：超出拒绝该条
ENTRY_CONTENT_MAX_BYTES = 10 * 1024 * 1024

# 沙箱允许的模块白名单
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


# ── 缓存 ────────────────────────────────────────────────────────────────


def script_cache_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"script-{digest}"


def _validate_script_url(url: str) -> bool:
    """脚本下载 URL 最小校验：仅 http/https 且 host 非内网 IP 字面量。

    本地实现（不复用 ott_rule_interpreter.validate_url）：rule 版做 DNS 解析
    且限 80/443 端口，下载路径不需要这么重，也避免测试依赖真实 DNS。
    域名形式 host 放行（公网性由 manifest 审核保证）；IP 字面量必须公网。
    """
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, OSError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False  # file:// 等 scheme 一律拒绝
    hostname = parsed.hostname
    if not hostname:
        return False
    hostname = hostname.lower().rstrip(".")
    if hostname in ("localhost", "localhost.localdomain"):
        return False
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return True  # 域名形式，放行
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        # CGNAT 共享地址空间（RFC 6598，100.64.0.0/10）不在 is_private 覆盖内，
        # 与 ott_rule_interpreter.validate_url 的策略对齐，显式拦截
        or (isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK)
    )


def _normalize_expected_checksum(expected: str) -> str:
    """归一化期望 checksum：容忍 'sha256:' 前缀与大小写，返回小写 hex。"""
    value = expected.strip().lower()
    if value.startswith("sha256:"):
        value = value[len("sha256:") :].strip()
    return value


def _checksum_matches(source: str, expected: str) -> bool:
    """脚本源码 sha256 与期望 checksum 比对；期望为空视为放行。"""
    expected = _normalize_expected_checksum(expected)
    if not expected:
        return True
    return hashlib.sha256(source.encode("utf-8")).hexdigest() == expected


class _ScriptTooLargeError(ValueError):
    """下载字节超过 SCRIPT_MAX_BYTES。"""


class ScriptCache:
    """脚本下载与缓存。"""

    def __init__(
        self,
        cache_dir: Path,
        http_client: httpx.Client,
        enabled: bool = True,
        ttl_seconds: int = 3600,
        router: "SmartRouteSelector | None" = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        # 智能路由：None = 保持固定降级（主 → jsDelivr），兼容旧调用
        self._router = router

    def get_script(
        self,
        url: str,
        ttl_seconds: int | None = None,
        *,
        expected_checksum: str = "",
    ) -> str | None:
        if not self._enabled:
            return None
        cache_key = script_cache_key(url)
        cached = self._read_cache(cache_key)
        ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
        if cached is not None and expected_checksum:
            # 缓存内容同样要过 checksum（缓存可能来自旧版本未校验下载）
            if not _checksum_matches(cached, expected_checksum):
                log_warning(
                    f"[ScriptCache] 缓存脚本 checksum 不匹配，重新下载: "
                    f"{redact_url(url)}"
                )
                cached = None
        if cached is not None:
            if not self._is_expired(cache_key, ttl):
                return cached
        return self._fetch_and_cache(cache_key, url, expected_checksum)

    def _fetch_and_cache(
        self, cache_key: str, url: str, expected_checksum: str = ""
    ) -> str | None:
        if not _validate_script_url(url):
            log_warning(f"[ScriptCache] 脚本 URL 非法: {redact_url(url)}")
            return self._read_cache(cache_key)
        try:
            source = self._download_limited(url, SCRIPT_MAX_BYTES)
        except _ScriptTooLargeError:
            log_warning(
                f"[ScriptCache] 脚本超过 {SCRIPT_MAX_BYTES} 字节上限: {redact_url(url)}"
            )
            return self._read_cache(cache_key)
        except (httpx.HTTPError, httpx.InvalidURL, OSError) as e:
            log_warning(f"[ScriptCache] 下载失败: {redact_url(url)} — {e}")
            return self._read_cache(cache_key)

        if expected_checksum and not _checksum_matches(source, expected_checksum):
            log_warning(
                f"[ScriptCache] 脚本 checksum 不匹配，拒绝缓存与执行: {redact_url(url)}"
            )
            return self._read_cache(cache_key)

        # AST 安全检查
        report = validate_script_source(source, url)
        if not report.valid:
            codes = [i.code for i in report.issues]
            log_warning(f"[ScriptCache] AST 检查失败: {redact_url(url)} — {codes}")
            return self._read_cache(cache_key)

        self._write_cache(cache_key, source)
        return source

    def _download_limited(self, url: str, max_bytes: int) -> str:
        """流式下载脚本，累计超过 max_bytes 立即中止（防主进程 OOM）。

        配置了智能路由时按实时延迟/连通性选路（原始 + jsDelivr + 前缀镜像）；
        否则保持固定降级（主地址 → jsDelivr CDN，GitHub raw 直连在国内网络
        常超时，2026-08-13 实测）；脚本超限/非 raw URL 不触发兜底。
        """
        if self._router is not None:
            last_error: BaseException | None = None
            for candidate in self._router.ordered_candidates(url):
                t0 = time.monotonic()
                try:
                    source = self._download_once(candidate, max_bytes)
                    self._router.record(
                        candidate, ok=True, latency=time.monotonic() - t0
                    )
                    return source
                except _ScriptTooLargeError:
                    raise
                except (httpx.HTTPError, httpx.InvalidURL, OSError) as e:
                    last_error = e
                    self._router.record(
                        candidate, ok=False, latency=time.monotonic() - t0
                    )
            raise last_error or httpx.ConnectError("所有候选路径均失败")
        try:
            return self._download_once(url, max_bytes)
        except _ScriptTooLargeError:
            raise
        except (httpx.HTTPError, httpx.InvalidURL, OSError):
            fallback = to_jsdelivr_url(url)
            if fallback:
                log_warning(
                    f"[ScriptCache] 主地址失败，jsDelivr CDN 降级: "
                    f"{redact_url(url)} → {redact_url(fallback)}"
                )
                return self._download_once(fallback, max_bytes)
            raise

    def _download_once(self, url: str, max_bytes: int) -> str:
        """单地址流式下载；iter_text() 返回 str，len() 是字符数而非 UTF-8 字节数，
        非 ASCII 内容可能绕过上限，必须按编码后的字节数累计。"""
        chunks: list[str] = []
        total = 0
        with self._client.stream("GET", url, timeout=10.0) as response:
            response.raise_for_status()
            for chunk in response.iter_text():
                total += len(chunk.encode("utf-8"))
                if total > max_bytes:
                    raise _ScriptTooLargeError(f"响应体超过 {max_bytes} 字节上限")
                chunks.append(chunk)
        return "".join(chunks)

    def cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.py"

    def _read_cache(self, cache_key: str) -> str | None:
        path = self.cache_path(cache_key)
        try:
            if not path.exists():
                return None
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_cache(self, cache_key: str, source: str) -> None:
        path = self.cache_path(cache_key)
        try:
            tmp_path = path.with_suffix(f"{path.suffix}.tmp")
            tmp_path.write_text(source, encoding="utf-8")
            tmp_path.replace(path)
        except OSError:
            pass

    def _is_expired(self, cache_key: str, ttl_seconds: int) -> bool:
        path = self.cache_path(cache_key)
        try:
            if not path.exists():
                return True
            mtime = path.stat().st_mtime
        except OSError:
            return True
        return (time.time() - mtime) > ttl_seconds


def _is_owner(path: Path) -> bool:
    """文件属主必须是当前用户，防其他用户预置替换脚本。"""
    if not hasattr(os, "getuid"):
        return True  # Windows 无 uid 概念，跳过
    try:
        return path.stat().st_uid == os.getuid()
    except OSError:
        return False


# ── 沙箱执行 ────────────────────────────────────────────────────────────


class ScriptSandbox:
    """受限的脚本执行环境（子进程隔离）。

    脚本在独立 Python 子进程中执行，通过 subprocess.Popen() 启动
    ott_script_runner.py。资源限制（内存/CPU/proc）由 runner 在子进程内设置。

    凭据注入（ADR-011 Phase 5.4）：``execute(secret_names=...)`` 时父进程
    从 token store 取值，经一次性 os.pipe() + pass_fds 传给子进程 ——
    不走环境变量（/proc/<pid>/environ 不可见）、不写入沙箱文件系统
    （Landlock 白名单之外）；子进程读取一次后 fd 即关闭。
    """

    def __init__(
        self,
        allowed_modules: frozenset[str] = ALLOWED_MODULES,
        enabled: bool = True,
        token_store: TokenStore | None = None,
    ) -> None:
        self._allowed = allowed_modules
        self._enabled = enabled
        self._token_store = token_store

    def execute(
        self,
        source: str,
        script_url: str,
        secret_names: list[str] | None = None,
        network_allowlist: list[str] | None = None,
        min_api_level: int | None = None,
    ) -> list[dict]:
        """执行脚本并返回 fetch_entries() 的结果（兼容便捷入口）。

        执行层失败（网络不可达、超时、非零退出、非法输出）折叠为空列表，
        保持既有调用方契约；需要区分「失败」与「成功但空」时用
        ``execute_strict``。
        """
        result = self.execute_strict(
            source,
            script_url,
            secret_names=secret_names,
            network_allowlist=network_allowlist,
            min_api_level=min_api_level,
        )
        return result if result is not None else []

    def execute_strict(
        self,
        source: str,
        script_url: str,
        secret_names: list[str] | None = None,
        network_allowlist: list[str] | None = None,
        min_api_level: int | None = None,
    ) -> list[dict] | None:
        """执行脚本并区分「失败（None）」与「成功但空（[]）」。

        None 仅表示执行层失败——联邦层据此把该 script 源计入刷新失败，
        断网时用户才能看到「刷新失败，当前显示缓存快照」，而不是把脚本
        静默当作空结果算成功。跳过型结果（脚本功能关闭 / API level 门槛
        不兼容）仍返回 []，因为那是主动跳过、不是网络失败。
        """
        if not self._enabled:
            return []
        if min_api_level is not None:
            try:
                if int(min_api_level) > CLIENT_API_LEVEL:
                    log_warning(
                        f"[ScriptSandbox] 脚本要求 API level {min_api_level}，"
                        f"客户端仅 {CLIENT_API_LEVEL}，跳过: {redact_url(script_url)}"
                    )
                    return []
            except (TypeError, ValueError):
                log_warning(
                    f"[ScriptSandbox] 非法 min_api_level，跳过: {redact_url(script_url)}"
                )
                return []
        secrets = self._resolve_secrets(secret_names)
        if secrets is None:
            return None
        # 私有临时目录（mkdtemp 默认 0700）+ 脚本文件 0600，防其他用户窥探或替换
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="ott-sandbox-"))
        except OSError as e:
            log_warning(f"[ScriptSandbox] 创建临时目录失败: {e}")
            return None
        tmp_path = tmp_dir / (
            f"script-{hashlib.sha256(script_url.encode()).hexdigest()[:16]}.py"
        )
        try:
            tmp_path.write_text(source, encoding="utf-8")
            os.chmod(tmp_path, 0o600)
            if not _is_owner(tmp_path):
                log_warning("[ScriptSandbox] 临时脚本属主校验失败，拒绝执行")
                return None
        except OSError as e:
            log_warning(f"[ScriptSandbox] 写临时脚本失败: {e}")
            return None

        try:
            return self._execute_in_subprocess(
                tmp_path,
                _script_authority(script_url),
                secrets,
                network_allowlist,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _resolve_secrets(self, secret_names: list[str] | None) -> dict[str, str] | None:
        """按声明解析凭据；任一缺失/非法 → 返回 None（整体失败）。"""
        if not secret_names:
            return {}
        if sys.platform == "win32":
            log_warning("[ScriptSandbox] Windows 不支持凭据 fd 注入，拒绝执行")
            return None
        store = self._token_store
        if store is None:
            from .secure_token_store import SecureTokenStore

            store = SecureTokenStore()
        resolved: dict[str, str] = {}
        for name in dict.fromkeys(secret_names):  # 去重且保序
            if not isinstance(name, str) or not name:
                log_warning("[ScriptSandbox] 非法凭据名，拒绝执行")
                return None
            value = store.get_token(name)
            if value is None:
                log_warning(f"[ScriptSandbox] 凭据缺失，拒绝执行: {name}")
                return None
            if len(value.encode("utf-8")) > PIPE_SECRET_MAX_BYTES:
                log_warning(f"[ScriptSandbox] 凭据 {name} 超出一次性管道容量，拒绝执行")
                return None
            resolved[name] = value
        return resolved

    def _execute_in_subprocess(
        self,
        script_path: Path,
        authority: str,
        secrets: dict[str, str] | None = None,
        network_allowlist: list[str] | None = None,
    ) -> list[dict] | None:
        """在子进程中执行脚本。

        凭据注入：secrets 非空时，每个凭据创建一次性 pipe（os.pipe()），
        父进程写入值后立即关闭写端，读端经 pass_fds 继承给子进程；
        {name: fd} 映射经 stdin JSON 传给 runner。子进程读取一次后
        fd 即关闭，值不落盘、不进环境变量。

        网络白名单：network_allowlist 经同一 stdin JSON 传给 runner，
        runner 在沙箱内 deny-by-default 强制。
        """
        runner_path = Path(__file__).parent / "ott_script_runner.py"
        read_fds: list[int] = []
        created_fds: list[int] = []
        # stdin JSON 恒构造（即使无 secrets/allowlist），runner 非 TTY 时读取
        config: dict[str, Any] = {
            "secrets": {},
            "network_allowlist": list(network_allowlist or []),
        }
        if secrets:
            fd_map: dict[str, int] = {}
            try:
                for name, value in secrets.items():
                    r, w = os.pipe()
                    created_fds.extend([r, w])
                    try:
                        payload = value.encode("utf-8")
                        written = 0
                        # 循环写：os.write 可能部分写入，必须写完全部字节
                        while written < len(payload):
                            written += os.write(w, memoryview(payload)[written:])
                    finally:
                        os.close(w)
                        created_fds.remove(w)
                    read_fds.append(r)
                    fd_map[name] = r
                config["secrets"] = {n: {"fd": fd} for n, fd in fd_map.items()}
            except OSError as e:
                for fd in created_fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                log_warning(f"[ScriptSandbox] 创建凭据管道失败: {e}")
                return None
        config_json = json.dumps(config)

        try:
            proc = subprocess.Popen(
                [sys.executable, str(runner_path), str(script_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                pass_fds=tuple(read_fds),
            )
        except (OSError, ValueError) as e:
            for fd in created_fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            log_warning(f"[ScriptSandbox] 子进程启动失败: {e}")
            return None
        # 子进程已继承读端；父进程读端立即关闭，防止 fd 泄漏
        for fd in created_fds:
            try:
                os.close(fd)
            except OSError:
                pass

        try:
            stdout, stderr = proc.communicate(
                input=config_json, timeout=SCRIPT_EXEC_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            log_warning(f"[ScriptSandbox] 脚本执行超时 ({SCRIPT_EXEC_TIMEOUT_S}s)")
            return None
        except OSError as e:
            log_warning(f"[ScriptSandbox] 子进程通信失败: {e}")
            return None

        if proc.returncode != 0:
            # 只取 stderr 最后一行（异常摘要）打一条单行日志：完整 traceback
            # 属于远端脚本内部错误，整段落盘会放大到 WARNING 里像客户端
            # 崩溃，且 DNS 失败这类高频场景日志滚得极快。截断到 400 字符。
            lines = [
                line.strip() for line in (stderr or "").splitlines() if line.strip()
            ]
            summary = lines[-1] if lines else f"stderr 空（{len(stderr or '')} 字节）"
            if len(summary) > 400:
                summary = summary[:400] + "…"
            log_warning(f"[ScriptSandbox] 脚本退出码 {proc.returncode}: {summary}")
            return None

        # stdout 上限（防子进程输出撑爆主进程内存）；text=True 下 len() 是
        # 字符数，必须按 UTF-8 字节数对比，避免多字节文本绕过上限
        if len(stdout.encode("utf-8")) > STDOUT_MAX_BYTES:
            log_warning(f"[ScriptSandbox] 脚本 stdout 超过 {STDOUT_MAX_BYTES} 上限")
            return None

        # 解析 stdout JSON
        try:
            raw_entries = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            log_warning("[ScriptSandbox] 脚本 stdout 不是合法 JSON")
            return None

        if not isinstance(raw_entries, list):
            return None

        return self._normalize_entries(raw_entries, authority)

    def _normalize_entries(self, raw_entries: list, authority: str) -> list[dict]:
        """将脚本返回的原始数据标准化为 entry 格式。

        authority 按脚本 URL 指纹命名空间化（与 _ScriptClient 一致）；
        source_key 是稳定的分组键，保持脚本自报值，不做命名空间化。
        """
        result = []
        for item in raw_entries:
            if isinstance(item, str):
                item = {"content": item}
            if not isinstance(item, dict):
                continue
            if "content" not in item:
                continue
            content = str(item.get("content", ""))
            if len(content.encode("utf-8")) > ENTRY_CONTENT_MAX_BYTES:
                log_warning(
                    f"[ScriptSandbox] 单条 entry 内容超过 "
                    f"{ENTRY_CONTENT_MAX_BYTES} 上限，丢弃"
                )
                continue
            entry = {
                "entry_id": item.get("entry_id")
                or hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
                "title": str(item.get("title", "")),
                "content": content,
                "char_count": len(content),
                "charCount": len(content),
                "content_mode": "inline",
                "current_revision_id": item.get("revision_id", "v1"),
                "source_key": item.get("source_key", "script"),
                "source_label": item.get("source_label", "脚本源"),
                "tags": item.get("tags", [])
                if isinstance(item.get("tags"), list)
                else [],
                "fetched_at": item.get("fetched_at", ""),
                "category": str(item.get("category", "")),
                "authority": authority,
            }
            normalized = normalize_summary(entry, authority)
            normalized["content"] = entry["content"]  # normalize 不保留 content
            result.append(normalized)
            if len(result) >= MAX_ENTRIES_PER_SCRIPT:
                break
        return result


# ── 便捷函数 ────────────────────────────────────────────────────────────


def execute_script(
    source: str,
    script_url: str,
    network_allowlist: list[str] | None = None,
    min_api_level: int | None = None,
) -> list[dict]:
    """一次性执行脚本并返回 entry 列表。"""
    sandbox = ScriptSandbox()
    return sandbox.execute(
        source,
        script_url,
        network_allowlist=network_allowlist,
        min_api_level=min_api_level,
    )
