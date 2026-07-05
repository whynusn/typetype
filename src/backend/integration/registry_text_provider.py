"""注册表文本提供器 - 从 CDN 注册表获取文本。

实现 TextProvider Protocol。动态文本通过 GitHub Actions CI 生成并推送至静态仓库，
客户端只读不写，不执行远程脚本。

缓存层设计：
- Phase 1a：磁盘缓存 + TTL 过期 + 离线兜底 + 原子写（tmp + replace）
- Phase 1b：stale-while-revalidate（过期时返回 stale + 后台刷新）

缓存文件布局：
- {cache_dir}/index.json          ← registry_index.json 的缓存
- {cache_dir}/content/{key}.json  ← 单篇正文缓存
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ..config.runtime_config import RegistryConfig
from ..models.dto.fetched_text import FetchedText
from ..models.dto.text_catalog_item import TextCatalogItem
from ..utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor


class RegistryTextProvider:
    """注册表文本提供器，实现 TextProvider 协议。"""

    def __init__(
        self,
        config: RegistryConfig,
        cache_dir: Path,
        http_client: httpx.Client | None = None,
        async_executor: "AsyncExecutor" | None = None,
    ):
        self._config = config
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client or httpx.Client(timeout=10.0)
        self._async_executor = async_executor
        # 后台刷新去重：防止同一 key 的多个过期请求触发重复刷新
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._refresh_locks_lock = threading.Lock()

    def get_catalog(self) -> list[TextCatalogItem]:
        data = self._fetch_registry_index()
        if data is None:
            return []
        sources = data.get("sources", [])
        if not isinstance(sources, list):
            return []
        return [
            TextCatalogItem(
                id=item.get("id", 0),
                source_key=item["source_key"],
                label=item.get("label", item["source_key"]),
                description=item.get("description", ""),
                has_ranking=bool(item.get("has_ranking", False)),
            )
            for item in sources
            if isinstance(item, dict) and item.get("source_key")
        ]

    def fetch_text_by_key(self, source_key: str) -> FetchedText | None:
        if not self._validate_source_key(source_key):
            return None
        data = self._fetch_content(source_key)
        if data is None:
            return None
        content = data.get("content", "")
        if not isinstance(content, str) or not content:
            return None
        content = self._sanitize_content(content)
        return FetchedText(
            content=content,
            text_id=data.get("text_id"),
            title=data.get("title", "") if isinstance(data.get("title"), str) else "",
        )

    def fetch_text_by_client_id(self, client_text_id: int) -> FetchedText | None:
        return None

    # ------------------------------------------------------------------
    # 网络获取（含缓存决策）
    # ------------------------------------------------------------------

    def _fetch_registry_index(self) -> dict | None:
        url = f"{self._config.primary_url}/registry_index.json"
        mirror_url = (
            f"{self._config.mirror_url}/registry_index.json"
            if self._config.mirror_url
            else None
        )
        return self._fetch_json_with_cache(
            cache_key="index", url=url, mirror_url=mirror_url
        )

    def _fetch_content(self, source_key: str) -> dict | None:
        url = f"{self._config.primary_url}/content/{source_key}.json"
        mirror_url = (
            f"{self._config.mirror_url}/content/{source_key}.json"
            if self._config.mirror_url
            else None
        )
        return self._fetch_json_with_cache(
            cache_key=f"content/{source_key}",
            url=url,
            mirror_url=mirror_url,
            max_bytes=self._config.max_content_bytes,
        )

    def _fetch_json_with_cache(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None = None,
        max_bytes: int = 0,
    ) -> dict | None:
        """带缓存决策的 JSON 获取。

        决策树：
        1. cache hit + 未过期 → 返回缓存
        2. cache hit + 过期 → 返回 stale + 后台刷新（stale-while-revalidate）
        3. cache miss → 打网络（primary → mirror fallback）
        4. 网络成功 → 写缓存并返回
        5. 网络失败 + 有 stale 缓存 → 返回 stale（无视 TTL 兜底）
        6. 完全无缓存 → None
        """
        cached = self._read_cache(cache_key)
        if cached is not None:
            if not self._is_cache_expired(cache_key):
                return cached
            # cache hit + expired → stale-while-revalidate
            self._maybe_refresh_in_background(cache_key, url, mirror_url, max_bytes)
            return cached

        data = self._fetch_json(url, max_bytes=max_bytes)
        if data is None and mirror_url:
            data = self._fetch_json(mirror_url, max_bytes=max_bytes)

        if data is not None:
            self._write_cache(cache_key, data)
            return data

        # 网络失败 + 有 stale 缓存 → 离线兜底
        if cached is not None:
            log_warning(f"[RegistryTextProvider] 网络失败，返回过期缓存: {cache_key}")
            return cached

        return None

    def _maybe_refresh_in_background(
        self,
        cache_key: str,
        url: str,
        mirror_url: str | None,
        max_bytes: int,
    ) -> None:
        """过期时启动后台刷新（stale-while-revalidate），去重防重复刷新。"""
        if self._async_executor is None:
            return

        # 获取该 key 的刷新锁（懒创建 + 去重）
        with self._refresh_locks_lock:
            lock = self._refresh_locks.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                self._refresh_locks[cache_key] = lock
            # 如果锁被持有，说明已有刷新在进行中，不再提交新任务
            if not lock.acquire(blocking=False):
                return  # 已有后台任务在处理

        def _refresh() -> None:
            try:
                data = self._fetch_json(url, max_bytes=max_bytes)
                if data is None and mirror_url:
                    data = self._fetch_json(mirror_url, max_bytes=max_bytes)
                if data is not None:
                    self._write_cache(cache_key, data)
                    log_info(f"[RegistryTextProvider] 后台刷新成功: {cache_key}")
                else:
                    log_warning(f"[RegistryTextProvider] 后台刷新失败: {cache_key}")
            except Exception:
                log_warning(f"[RegistryTextProvider] 后台刷新异常: {cache_key}")
            finally:
                lock.release()
                # 清理锁避免内存泄漏
                with self._refresh_locks_lock:
                    self._refresh_locks.pop(cache_key, None)

        self._async_executor.submit(_refresh)

    def _fetch_json(self, url: str, max_bytes: int = 0) -> dict | None:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            if max_bytes > 0 and len(response.content) > max_bytes:
                return None
            return response.json()
        except httpx.HTTPError:
            return None
        except (ValueError, TypeError, OSError):
            return None

    # ------------------------------------------------------------------
    # 缓存读写
    # ------------------------------------------------------------------

    def _cache_path(self, cache_key: str) -> Path:
        """缓存文件路径。cache_key 为 'index' 或 'content/{source_key}'。"""
        return self._cache_dir / f"{cache_key}.json"

    def _read_cache(self, cache_key: str) -> dict | None:
        """读取缓存文件，失败返回 None。"""
        path = self._cache_path(cache_key)
        try:
            if not path.exists():
                return None
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, cache_key: str, data: dict) -> None:
        """原子写入缓存文件（tmp + replace）。"""
        path = self._cache_path(cache_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(f"{path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path.replace(path)
        except OSError:
            pass  # 缓存写入失败不影响主流程

    def _is_cache_expired(self, cache_key: str) -> bool:
        """基于文件 mtime 判断缓存是否过期。"""
        path = self._cache_path(cache_key)
        try:
            if not path.exists():
                return True
            mtime = path.stat().st_mtime
        except OSError:
            return True
        return (time.time() - mtime) > self._config.cache_ttl_seconds

    # ------------------------------------------------------------------
    # 安全与清洗
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_source_key(key: str) -> bool:
        return bool(key) and "/" not in key and ".." not in key and "\\" not in key

    @staticmethod
    def _sanitize_content(content: str) -> str:
        return "".join(c for c in content if c >= " " or c in "\n\r\t")
