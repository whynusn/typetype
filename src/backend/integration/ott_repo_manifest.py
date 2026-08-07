"""OTT Repo manifest fetch + cache（控制面）。

复用 ott_cached_fetcher.py 的五层决策树模式：
    cache hit → fresh → return
    cache hit → stale → return cached + 后台刷新
    cache miss → fetch → write cache → return
    网络成功 → 原子写
    离线兜底 → 返回缓存（无视 TTL）

缓存键按 repo URL 派生（sha256 前 16 hex），TTL 取自订阅的
refresh_ttl_seconds。后台刷新走 AsyncExecutor + threading.Lock 去重。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ..config.runtime_config import RuntimeConfig, SourceRepoEntry
from ..utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor


def repo_cache_key(url: str) -> str:
    """派生 repo URL 对应的缓存文件名键。"""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def validate_repo_manifest(data: Any) -> dict | None:
    """校验并归一化一份 Repo Manifest。

    通过返回 dict（可能补全默认字段），失败返回 None。
    校验规则遵循 repo-manifest-spec-draft.md §Field rules。
    """
    if not isinstance(data, dict):
        return None
    for required in ("protocol", "version", "type", "repo_id", "name"):
        if not isinstance(data.get(required), str) or not data[required].strip():
            return None
    if data["protocol"] != "ott-repo":
        return None
    if data["type"] not in ("repository", "directory"):
        return None

    mirrors = data.get("mirrors")
    if not isinstance(mirrors, list) or not mirrors:
        return None
    normalized_mirrors = []
    for m in mirrors:
        if not isinstance(m, dict):
            continue
        m_url = m.get("url")
        if not isinstance(m_url, str) or not m_url.strip():
            continue
        normalized_mirrors.append(
            {
                "url": m_url.strip().rstrip("/"),
                "priority": int(m.get("priority", 1))
                if str(m.get("priority", "1")).isdigit()
                else 1,
            }
        )
    if not normalized_mirrors:
        return None

    sources = data.get("sources")
    if not isinstance(sources, list):
        sources = []
    normalized_sources = [_normalize_source(s) for s in sources if isinstance(s, dict)]
    normalized_sources = [s for s in normalized_sources if s is not None]

    trust = data.get("trust")
    normalized_trust: dict = {}
    if isinstance(trust, dict):
        sig = trust.get("signature")
        pubkey = trust.get("pubkey")
        if isinstance(sig, str) and sig.strip():
            normalized_trust["signature"] = sig.strip()
        if isinstance(pubkey, str) and pubkey.strip():
            normalized_trust["pubkey"] = pubkey.strip()
        required = trust.get("required")
        normalized_trust["required"] = bool(required)

    requires = data.get("requires")
    normalized_requires: dict = {}
    if isinstance(requires, dict):
        ott_core = requires.get("ott_core")
        if isinstance(ott_core, str) and ott_core.strip():
            normalized_requires["ott_core"] = ott_core.strip()
        feats = requires.get("client_features")
        if isinstance(feats, list):
            normalized_requires["client_features"] = [
                f for f in feats if isinstance(f, str)
            ]

    return {
        "protocol": "ott-repo",
        "version": str(data["version"]),
        "type": data["type"],
        "repo_id": str(data["repo_id"]).strip(),
        "name": str(data["name"]).strip(),
        "description": str(data.get("description") or ""),
        "maintainer": _normalize_maintainer(data.get("maintainer")),
        "license": str(data.get("license") or ""),
        "updated_at": str(data.get("updated_at") or ""),
        "mirrors": normalized_mirrors,
        "trust": normalized_trust,
        "requires": normalized_requires,
        "sources": normalized_sources,
    }


def _normalize_maintainer(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    name = value.get("name")
    homepage = value.get("homepage")
    result = {}
    if isinstance(name, str) and name.strip():
        result["name"] = name.strip()
    if isinstance(homepage, str) and homepage.strip():
        result["homepage"] = homepage.strip()
    return result


def _normalize_source(source: dict) -> dict | None:
    """归一化 manifest 中的一条 source 条目。"""
    kind = source.get("type")
    if kind not in (
        "ott-instance",
        "ott-rule",
        "ott-bridge",
        "ott-script",
        "repository-ref",
    ):
        return None

    if kind == "repository-ref":
        url = source.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return {
            "type": kind,
            "url": url.strip().rstrip("/"),
            "label": str(source.get("label") or ""),
            "tags": _normalize_tags(source.get("tags")),
        }

    if kind == "ott-script":
        url = source.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        checksum = source.get("checksum")
        return {
            "type": kind,
            "url": url.strip(),
            "label": str(source.get("label") or ""),
            "checksum": str(checksum) if isinstance(checksum, str) else "",
            "tags": _normalize_tags(source.get("tags")),
        }

    if kind == "ott-instance":
        authority = source.get("authority")
        if not isinstance(authority, str) or not authority.strip():
            return None
        endpoints = source.get("endpoints")
        norm_endpoints = _normalize_endpoints(endpoints)
        if not norm_endpoints:
            # 无有效端点时，用 source 内声明的 mirrors 不可用；标记空
            return None
        return {
            "type": kind,
            "authority": authority.strip(),
            "label": str(source.get("label") or authority),
            "endpoints": norm_endpoints,
            "tags": _normalize_tags(source.get("tags")),
            "default_enabled": bool(source.get("default_enabled", True)),
        }

    if kind == "ott-rule":
        rule_id = source.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            return None
        return {
            "type": kind,
            "rule_id": rule_id.strip(),
            "label": str(source.get("label") or rule_id),
            "rule": source.get("rule") if isinstance(source.get("rule"), dict) else {},
            "tags": _normalize_tags(source.get("tags")),
        }

    if kind == "ott-bridge":
        bridge_kind = source.get("bridge_kind")
        if not isinstance(bridge_kind, str) or not bridge_kind.strip():
            return None
        endpoint = source.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint.strip():
            return None
        return {
            "type": kind,
            "bridge_kind": bridge_kind.strip(),
            "endpoint": endpoint.strip().rstrip("/"),
            "label": str(source.get("label") or bridge_kind),
            "requires_credentials": bool(source.get("requires_credentials", False)),
            "tags": _normalize_tags(source.get("tags")),
        }

    return None


def _normalize_endpoints(endpoints: Any) -> list[dict]:
    if not isinstance(endpoints, list):
        return []
    result = []
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        url = ep.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        profile = ep.get("profile")
        if profile not in ("static", "service"):
            profile = "static"
        priority_raw = ep.get("priority", 1)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            priority = 1
        result.append(
            {
                "url": url.strip().rstrip("/"),
                "profile": profile,
                "priority": max(1, priority),
            }
        )
    return sorted(result, key=lambda e: e["priority"])


def _normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    return [str(t) for t in tags if isinstance(t, str) and str(t).strip()]


class RepoManifestCache:
    """OTT Repo manifest 拉取与缓存组件。

    每个订阅 URL 独立缓存，TTL 取自订阅设置。
    """

    def __init__(
        self,
        cache_dir: Path,
        http_client: httpx.Client,
        async_executor: "AsyncExecutor | None",
        runtime_config: "RuntimeConfig | None" = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = http_client
        self._async_executor = async_executor
        self._runtime_config = runtime_config
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._refresh_locks_lock = threading.Lock()

    def get_manifest(self, repo: SourceRepoEntry) -> dict | None:
        """获取 manifest：fresh 命中直接返回；stale 命中返回缓存并触发后台刷新。"""
        if not repo.url:
            return None
        cache_key = repo_cache_key(repo.url)
        cached = self._read_cache(cache_key)
        if cached is not None:
            if not self._is_expired(cache_key, repo.refresh_ttl_seconds):
                return cached
            self._maybe_refresh(cache_key, repo)
            return cached

        return self._fetch_and_cache(cache_key, repo)

    def refresh_manifest(self, repo: SourceRepoEntry) -> dict | None:
        """强制刷新 manifest（忽略缓存）。"""
        if not repo.url:
            return None
        cache_key = repo_cache_key(repo.url)
        return self._fetch_and_cache(cache_key, repo)

    def _fetch_and_cache(self, cache_key: str, repo: SourceRepoEntry) -> dict | None:
        data = self._fetch_manifest(repo.url)
        if data is None:
            # 网络失败：离线兜底返回缓存（无视 TTL）
            return self._read_cache(cache_key)
        validated = validate_repo_manifest(data)
        if validated is None:
            log_warning(f"[RepoManifest] manifest 校验失败: {repo.url}")
            return self._read_cache(cache_key)
        self._write_cache(cache_key, validated)
        # 签名校验并更新订阅的 trust_state（TOFU）
        self._verify_trust(validated, repo)
        return validated

    def _fetch_manifest(self, url: str) -> dict | None:
        # 支持 file:// 协议读取本地文件（内置 fallback manifest）
        if url.startswith("file://"):
            return self._fetch_local_manifest(url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            log_warning(f"[RepoManifest] HTTP 请求失败: {url} — {e}")
            return None
        except (ValueError, TypeError, OSError) as e:
            log_warning(f"[RepoManifest] 响应解析失败: {url} — {e}")
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _fetch_local_manifest(url: str) -> dict | None:
        """从 file:// URL 读取本地 manifest。"""
        try:
            parsed = urlparse(url)
            path = Path(parsed.path)
            if not path.exists():
                log_warning(f"[RepoManifest] 本地文件不存在: {path}")
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as e:
            log_warning(f"[RepoManifest] 本地文件读取失败: {url} — {e}")
            return None
        if not isinstance(data, dict):
            return None
        # 替换内置路径占位符 __BUILTIN_DIR__
        return RepoManifestCache._resolve_builtin_paths(data, path.parent)

    @staticmethod
    def _resolve_builtin_paths(data: dict, base_dir: Path) -> dict:
        """将 manifest 中的 __BUILTIN_DIR__ 占位符替换为实际路径。"""
        import copy

        result = copy.deepcopy(data)
        str_data = json.dumps(result)
        if "__BUILTIN_DIR__" in str_data:
            str_data = str_data.replace("__BUILTIN_DIR__", str(base_dir))
            return json.loads(str_data)
        return result

    def _maybe_refresh(self, cache_key: str, repo: SourceRepoEntry) -> None:
        lock = self._acquire_refresh_lock(cache_key)
        if lock is None:
            return

        def refresh() -> None:
            try:
                data = self._fetch_manifest(repo.url)
                if data is not None:
                    validated = validate_repo_manifest(data)
                    if validated is not None:
                        self._write_cache(cache_key, validated)
                        self._verify_trust(validated, repo)
                        log_info(f"[RepoManifest] 后台刷新成功: {repo.url}")
                    else:
                        log_warning(f"[RepoManifest] 后台刷新校验失败: {repo.url}")
                else:
                    log_warning(f"[RepoManifest] 后台刷新网络失败: {repo.url}")
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

    def cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _read_cache(self, cache_key: str) -> dict | None:
        path = self.cache_path(cache_key)
        try:
            if not path.exists():
                return None
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, cache_key: str, data: dict) -> None:
        path = self.cache_path(cache_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(f"{path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

    def clear_cache(self, url: str | None = None) -> None:
        """清除缓存。url 为 None 全部清除，否则只清除指定 repo。"""
        import shutil

        try:
            if url is None:
                if self._cache_dir.exists():
                    shutil.rmtree(self._cache_dir)
                    self._cache_dir.mkdir(parents=True, exist_ok=True)
            else:
                path = self.cache_path(repo_cache_key(url))
                if path.exists():
                    path.unlink()
        except OSError:
            log_warning("[RepoManifest] 清除缓存失败")

    def _verify_trust(self, manifest: dict, repo: SourceRepoEntry) -> None:
        """校验 manifest 签名并更新 repo.trust_state（TOFU）。"""
        if self._runtime_config is None:
            return
        trust = manifest.get("trust") or {}
        signature = trust.get("signature", "")
        pubkey = trust.get("pubkey", "")

        if not signature or not pubkey:
            # 无签名信息 → 未验证
            self._runtime_config.set_source_repo_trust(repo.url, "unverified")
            return

        try:
            valid = self._verify_ed25519_signature(manifest, pubkey, signature)
        except Exception as e:
            log_warning(f"[RepoManifest] 签名校验异常: {repo.url} — {e}")
            self._runtime_config.set_source_repo_trust(repo.url, "failed")
            return

        if not valid:
            self._runtime_config.set_source_repo_trust(repo.url, "failed")
            return

        # TOFU：首次信任固定公钥，变更则标记 failed
        if not repo.pinned_pubkey:
            # 首次订阅：固定公钥
            self._runtime_config.set_source_repo_trust(
                repo.url, "verified", pinned_pubkey=pubkey
            )
        elif repo.pinned_pubkey != pubkey:
            # 公钥变更 → 验证失败（需用户显式确认）
            self._runtime_config.set_source_repo_trust(repo.url, "failed")
            log_warning(f"[RepoManifest] 公钥变更: {repo.url}")
        else:
            self._runtime_config.set_source_repo_trust(repo.url, "verified")

    @staticmethod
    def _verify_ed25519_signature(
        manifest: dict, pubkey_str: str, signature: str
    ) -> bool:
        """验证 ed25519 签名。

        pubkey 格式: "ed25519:<hex>" 或裸 hex；签名格式: "ed25519:<hex>" 或裸 hex。
        签名对象为剔除 trust 字段的 manifest 的 canonical JSON。
        """
        # 解析公钥
        pubkey_clean = pubkey_str.split(":", 1)[1] if ":" in pubkey_str else pubkey_str
        sig_clean = signature.split(":", 1)[1] if ":" in signature else signature

        try:
            pubkey_bytes = bytes.fromhex(pubkey_clean.strip())
            sig_bytes = bytes.fromhex(sig_clean.strip())
        except ValueError:
            return False

        # 构建 canonical bytes：剔除 trust 字段后的 manifest
        canonical = {k: v for k, v in manifest.items() if k != "trust"}
        canonical_bytes = json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            key.verify(sig_bytes, canonical_bytes)
            return True
        except (InvalidSignature, ValueError, Exception):
            return False
