from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ..config.runtime_config import OttConfig
from ..utils.logger import log_info, log_warning
from .ott_normalization import local_path_from_file_uri, redact_url, to_jsdelivr_url

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor


class OttCachedFetcher:
    def __init__(
        self,
        config: OttConfig,
        cache_dir: Path,
        http_client: httpx.Client,
        async_executor: AsyncExecutor | None,
    ) -> None:
        self._config = config
        self._cache_dir = cache_dir
        self._client = http_client
        self._async_executor = async_executor
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._refresh_locks_lock = threading.Lock()

    def fetch_json_with_cache(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None = None,
        max_bytes: int = 0,
        force: bool = False,
    ) -> dict | None:
        if force:
            # 手动刷新：绕过缓存读，直接拉取并写回（失败不读旧缓存）
            data = self._fetch_json(url, max_bytes=max_bytes)
            if data is None and mirror_url:
                data = self._fetch_json(mirror_url, max_bytes=max_bytes)
            if data is not None:
                self.write_cache(cache_key, data)
            return data
        cached = self.read_cache(cache_key)
        if cached is not None:
            if not self.is_cache_expired(cache_key):
                return cached
            self._maybe_refresh_json(cache_key, url, mirror_url, max_bytes)
            return cached

        data = self._fetch_json(url, max_bytes=max_bytes)
        if data is None and mirror_url:
            data = self._fetch_json(mirror_url, max_bytes=max_bytes)
        if data is not None:
            self.write_cache(cache_key, data)
            return data
        return None

    def fetch_text_with_cache(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None = None,
        max_bytes: int = 0,
        force: bool = False,
    ) -> str | None:
        if force:
            # 手动刷新：绕过缓存读，直接拉取并写回（失败不读旧缓存）
            content = self._fetch_text(url, max_bytes=max_bytes)
            if content is None and mirror_url:
                content = self._fetch_text(mirror_url, max_bytes=max_bytes)
            if content is not None:
                self.write_cache(cache_key, {"content": content})
            return content
        cached = self.read_cache(cache_key)
        if cached is not None and isinstance(cached.get("content"), str):
            if not self.is_cache_expired(cache_key):
                return str(cached["content"])
            self._maybe_refresh_text(cache_key, url, mirror_url, max_bytes)
            return str(cached["content"])

        content = self._fetch_text(url, max_bytes=max_bytes)
        if content is None and mirror_url:
            content = self._fetch_text(mirror_url, max_bytes=max_bytes)
        if content is not None:
            self.write_cache(cache_key, {"content": content})
            return content
        return None

    def _maybe_refresh_json(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None,
        max_bytes: int,
    ) -> None:
        lock = self._acquire_refresh_lock(cache_key)
        if lock is None:
            return

        def refresh() -> None:
            try:
                data = self._fetch_json(url, max_bytes=max_bytes)
                if data is None and mirror_url:
                    data = self._fetch_json(mirror_url, max_bytes=max_bytes)
                if data is not None:
                    self.write_cache(cache_key, data)
                    log_info(f"[OttCachedFetcher] 后台刷新成功: {cache_key}")
                else:
                    log_warning(f"[OttCachedFetcher] 后台刷新失败: {cache_key}")
            finally:
                self._release_refresh_lock(cache_key, lock)

        self._submit_refresh(refresh)

    def _maybe_refresh_text(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None,
        max_bytes: int,
    ) -> None:
        lock = self._acquire_refresh_lock(cache_key)
        if lock is None:
            return

        def refresh() -> None:
            try:
                content = self._fetch_text(url, max_bytes=max_bytes)
                if content is None and mirror_url:
                    content = self._fetch_text(mirror_url, max_bytes=max_bytes)
                if content is not None:
                    self.write_cache(cache_key, {"content": content})
                    log_info(f"[OttCachedFetcher] 后台刷新成功: {cache_key}")
                else:
                    log_warning(f"[OttCachedFetcher] 后台刷新失败: {cache_key}")
            finally:
                self._release_refresh_lock(cache_key, lock)

        self._submit_refresh(refresh)

    def _submit_refresh(self, refresh: Callable[[], None]) -> None:
        if self._async_executor is None:
            return
        self._async_executor.submit(refresh)

    def _acquire_refresh_lock(self, cache_key: str) -> threading.Lock | None:
        if self._async_executor is None:
            return None
        with self._refresh_locks_lock:
            lock = self._refresh_locks.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                self._refresh_locks[cache_key] = lock
            if not lock.acquire(blocking=False):
                return None
            return lock

    def _release_refresh_lock(self, cache_key: str, lock: threading.Lock) -> None:
        lock.release()
        with self._refresh_locks_lock:
            self._refresh_locks.pop(cache_key, None)

    def _fetch_json(self, url: str, max_bytes: int = 0) -> dict | None:
        """拉取 JSON，主地址失败时 jsDelivr CDN 降级（GitHub raw 超时兜底）。"""
        if url.startswith("file://"):
            return self._read_local_json(url, max_bytes=max_bytes)
        data = self._fetch_json_once(url, max_bytes=max_bytes)
        if data is None:
            fallback = to_jsdelivr_url(url)
            if fallback:
                log_warning(
                    f"[OttCachedFetcher] 主地址失败，jsDelivr CDN 降级: "
                    f"{redact_url(url)} → {redact_url(fallback)}"
                )
                data = self._fetch_json_once(fallback, max_bytes=max_bytes)
        return data

    def _fetch_json_once(self, url: str, max_bytes: int = 0) -> dict | None:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            headers = getattr(response, "headers", None)
            if max_bytes > 0 and headers is not None:
                try:
                    declared = int(headers.get("content-length", -1))
                except (TypeError, ValueError):
                    declared = -1
                if declared > max_bytes:
                    log_warning(
                        f"[OttCachedFetcher] 响应体超限: {redact_url(url)} ({declared} > {max_bytes})"
                    )
                    return None
            if max_bytes > 0 and len(response.content) > max_bytes:
                log_warning(
                    f"[OttCachedFetcher] 响应体超限: {redact_url(url)} ({len(response.content)} > {max_bytes})"
                )
                return None
            data = response.json()
        except httpx.HTTPError as e:
            log_warning(f"[OttCachedFetcher] HTTP 请求失败: {redact_url(url)} — {e}")
            return None
        except (ValueError, TypeError, OSError) as e:
            log_warning(f"[OttCachedFetcher] 响应解析失败: {redact_url(url)} — {e}")
            return None
        return data if isinstance(data, dict) else None

    def _fetch_text(self, url: str, max_bytes: int = 0) -> str | None:
        """拉取文本，主地址失败时 jsDelivr CDN 降级（GitHub raw 超时兜底）。"""
        if url.startswith("file://"):
            return self._read_local_text(url, max_bytes=max_bytes)
        content = self._fetch_text_once(url, max_bytes=max_bytes)
        if content is None:
            fallback = to_jsdelivr_url(url)
            if fallback:
                log_warning(
                    f"[OttCachedFetcher] 主地址失败，jsDelivr CDN 降级: "
                    f"{redact_url(url)} → {redact_url(fallback)}"
                )
                content = self._fetch_text_once(fallback, max_bytes=max_bytes)
        return content

    def _fetch_text_once(self, url: str, max_bytes: int = 0) -> str | None:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            headers = getattr(response, "headers", None)
            if max_bytes > 0 and headers is not None:
                try:
                    declared = int(headers.get("content-length", -1))
                except (TypeError, ValueError):
                    declared = -1
                if declared > max_bytes:
                    log_warning(
                        f"[OttCachedFetcher] 响应体超限: {redact_url(url)} ({declared} > {max_bytes})"
                    )
                    return None
            if max_bytes > 0 and len(response.content) > max_bytes:
                log_warning(
                    f"[OttCachedFetcher] 响应体超限: {redact_url(url)} ({len(response.content)} > {max_bytes})"
                )
                return None
        except httpx.HTTPError as e:
            log_warning(f"[OttCachedFetcher] HTTP 请求失败: {redact_url(url)} — {e}")
            return None
        return response.text

    @staticmethod
    def _read_local_json(url: str, max_bytes: int = 0) -> dict | None:
        try:
            path = local_path_from_file_uri(url)
            if not path.exists():
                return None
            # 先查文件大小，超限不解析（避免大文件先读入内存）
            if max_bytes > 0 and path.stat().st_size > max_bytes:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_local_text(url: str, max_bytes: int = 0) -> str | None:
        try:
            path = local_path_from_file_uri(url)
            if not path.exists():
                return None
            text = path.read_text(encoding="utf-8")
            if max_bytes > 0 and len(text) > max_bytes:
                text = text[:max_bytes]
        except (OSError, ValueError):
            return None
        return text

    def cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def clear_cache(self) -> None:
        import shutil

        try:
            if self._cache_dir.exists():
                shutil.rmtree(self._cache_dir)
                self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_warning("[OttCachedFetcher] 清除缓存失败")

    def read_cache(self, cache_key: str) -> dict | None:
        path = self.cache_path(cache_key)
        try:
            if not path.exists():
                return None
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def write_cache(self, cache_key: str, data: dict) -> None:
        path = self.cache_path(cache_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(f"{path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path.replace(path)
        except OSError:
            pass

    def is_cache_expired(self, cache_key: str) -> bool:
        path = self.cache_path(cache_key)
        try:
            if not path.exists():
                return True
            mtime = path.stat().st_mtime
        except OSError:
            return True
        return (time.time() - mtime) > self._config.cache_ttl_seconds
