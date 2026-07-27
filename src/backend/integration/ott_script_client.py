"""OTT Repo ott-script 下载、缓存、沙箱执行。

脚本必须定义 fetch_entries() -> list[dict]，返回标准化 entry 列表。
沙箱限制：
- 仅允许白名单模块（httpx/json/Crypto/bs4 等）
- 禁止文件系统写入（除临时目录）
- 禁止子进程/网络监听
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ..utils.logger import log_info, log_warning
from .ott_normalization import normalize_summary
from .ott_script_safety import validate_script_source

if TYPE_CHECKING:
    pass

# ── 常量 ────────────────────────────────────────────────────────────────

SCRIPT_MAX_BYTES = 256 * 1024  # 256 KB
SCRIPT_EXEC_TIMEOUT_S = 30.0
MAX_ENTRIES_PER_SCRIPT = 1000

# 沙箱允许的模块白名单
ALLOWED_MODULES = frozenset({
    "builtins",
    "json",
    "re",
    "time",
    "datetime",
    "hashlib",
    "base64",
    "urllib",
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
})


# ── 缓存 ────────────────────────────────────────────────────────────────

def script_cache_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"script-{digest}"


class ScriptCache:
    """脚本下载与缓存。"""

    def __init__(self, cache_dir: Path, http_client: httpx.Client) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client

    def get_script(self, url: str, ttl_seconds: int = 3600) -> str | None:
        cache_key = script_cache_key(url)
        cached = self._read_cache(cache_key)
        if cached is not None:
            if not self._is_expired(cache_key, ttl_seconds):
                return cached
        return self._fetch_and_cache(cache_key, url)

    def _fetch_and_cache(self, cache_key: str, url: str) -> str | None:
        try:
            response = self._client.get(url, timeout=10.0)
            response.raise_for_status()
            source = response.text[:SCRIPT_MAX_BYTES]
        except (httpx.HTTPError, httpx.InvalidURL, OSError) as e:
            log_warning(f"[ScriptCache] 下载失败: {url} — {e}")
            return self._read_cache(cache_key)

        # AST 安全检查
        report = validate_script_source(source, url)
        if not report.valid:
            codes = [i.code for i in report.issues]
            log_warning(f"[ScriptCache] AST 检查失败: {url} — {codes}")
            return self._read_cache(cache_key)

        self._write_cache(cache_key, source)
        return source

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


# ── 沙箱执行 ────────────────────────────────────────────────────────────

class ScriptSandbox:
    """受限的脚本执行环境。"""

    def __init__(self, allowed_modules: frozenset[str] = ALLOWED_MODULES) -> None:
        self._allowed = allowed_modules

    def execute(self, source: str, script_url: str) -> list[dict]:
        """执行脚本并返回 fetch_entries() 的结果。"""
        # 构建受限 globals
        safe_globals = {
            "__builtins__": self._build_safe_builtins(),
            "__name__": "__ott_script__",
        }

        # 预导入白名单模块
        for mod_name in self._allowed:
            if mod_name in ("builtins",):
                continue
            try:
                parts = mod_name.split(".")
                mod = __import__(mod_name, fromlist=[parts[-1]])
                safe_globals[parts[0]] = mod
            except ImportError:
                pass

        # 编译 + 执行
        try:
            code = compile(source, filename=f"<ott-script:{script_url}>", mode="exec")
        except SyntaxError:
            return []

        exec(code, safe_globals)

        # 调用 fetch_entries()
        fetch_fn = safe_globals.get("fetch_entries")
        if not callable(fetch_fn):
            return []

        try:
            result = fetch_fn()
        except Exception as e:
            log_warning(f"[ScriptSandbox] fetch_entries 异常: {e}")
            return []

        if not isinstance(result, list):
            return []

        return self._normalize_entries(result)

    def _build_safe_builtins(self) -> dict:
        """构建受限的 builtins 字典。"""
        import builtins as _builtins
        safe = {}
        for name in dir(_builtins):
            if name in ("eval", "exec", "compile", "__import__", "open"):
                continue
            obj = getattr(_builtins, name)
            # 允许 print 但重定向到日志
            if name == "print":
                safe[name] = _safe_print
                continue
            safe[name] = obj
        return safe

    def _normalize_entries(self, raw_entries: list) -> list[dict]:
        """将脚本返回的原始数据标准化为 entry 格式。"""
        result = []
        for item in raw_entries:
            if isinstance(item, str):
                item = {"content": item}
            if not isinstance(item, dict):
                continue
            if "content" not in item:
                continue
            entry = {
                "entry_id": item.get("entry_id") or hashlib.sha256(
                    str(item.get("content", "")).encode("utf-8")
                ).hexdigest()[:16],
                "title": str(item.get("title", "")),
                "content": str(item.get("content", "")),
                "char_count": len(str(item.get("content", ""))),
                "charCount": len(str(item.get("content", ""))),
                "content_mode": "inline",
                "current_revision_id": item.get("revision_id", "v1"),
                "source_key": item.get("source_key", "script"),
                "source_label": item.get("source_label", "脚本源"),
                "tags": item.get("tags", []) if isinstance(item.get("tags"), list) else [],
                "fetched_at": item.get("fetched_at", ""),
                "category": str(item.get("category", "")),
                "authority": "script",
            }
            normalized = normalize_summary(entry, "script")
            normalized["content"] = entry["content"]  # normalize 不保留 content
            result.append(normalized)
            if len(result) >= MAX_ENTRIES_PER_SCRIPT:
                break
        return result


def _safe_print(*args, **kwargs) -> None:
    """沙箱内的 print 重定向到日志。"""
    msg = " ".join(str(a) for a in args)
    log_info(f"[ott-script] {msg}")


# ── 便捷函数 ────────────────────────────────────────────────────────────

def execute_script(source: str, script_url: str) -> list[dict]:
    """一次性执行脚本并返回 entry 列表。"""
    sandbox = ScriptSandbox()
    return sandbox.execute(source, script_url)
