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
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..config.runtime_config import RuntimeConfig, SourceRepoEntry
from ..utils.logger import log_info, log_warning
from .ott_normalization import local_path_from_file_uri, redact_url

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor


def repo_cache_key(url: str) -> str:
    """派生 repo URL 对应的缓存文件名键。"""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def manifest_hash(manifest: dict) -> str:
    """manifest 的 sha256（canonical JSON），用作 TUF-lite snapshot 链参照。

    canonical 形式与签名校验一致：sort_keys + ensure_ascii=False + compact
    separators。链式设计（ADR-011 Phase 3.6）：下一版 manifest 的
    ``snapshot_hash`` 必须等于当前已接受 manifest 的此 hash。
    """
    canonical = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_snapshot_hash(value: str) -> str:
    """归一化 snapshot_hash 用于比较：容忍可选 ``sha256:`` 前缀、大小写。

    生产方与客户端前缀格式不一致时不应误判回滚，故比较前剥离前缀。
    """
    return value.removeprefix("sha256:").strip().lower()


def _normalize_revocations(value: Any) -> list[dict]:
    """归一化 revocations 列表（ADR-011 Phase 2.7）。

    条目为 dict，可含 ``content_hash``（内容级撤销 → 本地屏蔽）与
    ``pubkey``（key 级撤销 → 信任降级）字段；非法/空条目丢弃。
    """
    if not isinstance(value, list):
        return []
    result: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entry: dict = {}
        ch = item.get("content_hash")
        if isinstance(ch, str) and ch.strip():
            entry["content_hash"] = ch.strip()
        pk = item.get("pubkey")
        if isinstance(pk, str) and pk.strip():
            entry["pubkey"] = pk.strip()
        if entry:
            result.append(entry)
    return result


def validate_repo_manifest(data: Any) -> dict | None:
    """校验并归一化一份 Repo Manifest。

    通过返回 dict（可能补全默认字段），失败返回 None。
    校验规则遵循 repo-manifest-spec.md §Field rules。
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
        # ADR-011 Phase 2.7/3.6：TUF-lite 与撤销字段（可选，缺失即旧行为）
        "revocations": _normalize_revocations(data.get("revocations")),
        "expires_at": str(data.get("expires_at") or ""),
        "snapshot_hash": str(data.get("snapshot_hash") or ""),
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


def _normalize_script_permissions(value: Any) -> dict:
    """归一化脚本源 permissions：仅保留 network/secrets 的非空字符串列表。"""
    if not isinstance(value, dict):
        return {}
    result: dict = {}
    network = value.get("network")
    if isinstance(network, list):
        result["network"] = [h for h in network if isinstance(h, str) and h.strip()]
    secrets = value.get("secrets")
    if isinstance(secrets, list):
        result["secrets"] = [s for s in secrets if isinstance(s, str) and s.strip()]
    return result


def _normalize_script_rights(value: Any) -> dict:
    """归一化脚本源 rights：仅保留正整数 min_api_level。"""
    if not isinstance(value, dict):
        return {}
    result: dict = {}
    level = value.get("min_api_level")
    if isinstance(level, int) and not isinstance(level, bool) and level > 0:
        result["min_api_level"] = level
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
            # ADR-011 Phase 2.2/2.6：脚本源权限与 API level（运行时强制）
            "permissions": _normalize_script_permissions(source.get("permissions")),
            "rights": _normalize_script_rights(source.get("rights")),
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
        cached = self._read_validated_cache(cache_key)
        if cached is not None:
            # TTL 过期或 manifest 自身 expires_at 过期（TUF-lite）都算 stale：
            # 返回缓存 + 后台刷新（stale-while-revalidate，不硬失败）。
            if not self._is_expired(
                cache_key, repo.refresh_ttl_seconds
            ) and not self._manifest_expired(cached):
                return cached
            self._maybe_refresh(cache_key, repo)
            return cached

        return self._fetch_and_cache(cache_key, repo)

    def load_local_manifest(self, repo: SourceRepoEntry) -> dict | None:
        """file:// 订阅直接读取本地 manifest，绕过缓存（本地文件即最新源）。"""
        if not repo.url.startswith("file://"):
            return self.get_manifest(repo)
        data = self._fetch_local_manifest(repo.url)
        if data is None:
            return None
        return validate_repo_manifest(data)

    def refresh_manifest(self, repo: SourceRepoEntry) -> dict | None:
        """强制刷新 manifest（忽略缓存）。"""
        if not repo.url:
            return None
        cache_key = repo_cache_key(repo.url)
        return self._fetch_and_cache(cache_key, repo)

    def _fetch_and_cache(self, cache_key: str, repo: SourceRepoEntry) -> dict | None:
        data, etag = self._fetch_manifest_with_mirrors(repo, cache_key)
        if data is None:
            # 网络失败：离线兜底返回缓存（无视 TTL）
            return self._read_validated_cache(cache_key)
        _, served = self._accept_manifest(cache_key, repo, data, etag)
        return served

    def _accept_manifest(
        self, cache_key: str, repo: SourceRepoEntry, data: dict, etag: str
    ) -> tuple[bool, dict | None]:
        """校验 + TUF-lite 检查 + 先验签后落盘 + 撤销/信任更新。

        ADR-011 Phase 2.7/3.6 语义（链式 snapshot 设计）：
        - 校验失败 / expires_at 过期 / snapshot_hash 回滚 → 拒绝新 manifest，
          回退旧缓存（服务 stale），不替换缓存；
        - 先验签后落盘：签名 failed、首次有效签名（待 UI 确认）、公钥变更
          （待重新确认）、key 级撤销、pending 粘性 → 拒绝替换缓存，回退旧
          缓存（TOFU 未确认的内容不服务，订阅即信任边界）；
        - 只有被接受且签名验证通过的 manifest 才应用 revocations（撤销清单
          仅来自签名生效的 manifest，防伪造屏蔽投毒）；无签名 manifest
          （unverified）接受但不应用 revocations；
        - 验签与 snapshot 链参照均以网络原始 dict 为口径：canonical 字节必须
          与生产方签名/快照链一致（归一化重构会改变字节导致验签必失败），
          缓存存储原始内容，读取时再归一化；
        - last_snapshot_hash 恒记录最近一次被接受 manifest 的原始 hash。

        Returns:
            (True, new_manifest)  新 manifest 已接受；
            (False, served)      被拒绝，served 为回退的旧缓存（可为 None）。
        """
        validated = validate_repo_manifest(data)
        if validated is None:
            log_warning(f"[RepoManifest] manifest 校验失败: {redact_url(repo.url)}")
            return False, self._read_validated_cache(cache_key)
        if self._manifest_expired(validated):
            # 过期内容不得作为 fresh 使用：保留旧缓存
            log_warning(
                f"[RepoManifest] manifest 已过期(expires_at)，保留旧缓存: "
                f"{redact_url(repo.url)}"
            )
            return False, self._read_validated_cache(cache_key)
        if self._check_snapshot_rollback(cache_key, repo, validated):
            log_warning(
                f"[RepoManifest] snapshot 回滚检测，拒绝替换缓存: "
                f"{redact_url(repo.url)}"
            )
            return False, self._read_validated_cache(cache_key)
        # 先验签后落盘：信任判定未达接受条件一律拒绝替换缓存（服务旧缓存）
        trust_result = self._verify_trust(data, repo)
        if trust_result not in ("verified", "unverified"):
            log_warning(
                f"[RepoManifest] 信任判定 {trust_result}，拒绝替换缓存: "
                f"{redact_url(repo.url)}"
            )
            return False, self._read_validated_cache(cache_key)
        # 接受：缓存网络原始内容（字节口径与生产方一致），推进链参照
        self._write_cache(cache_key, data)
        if self._runtime_config is not None:
            self._runtime_config.update_source_repo_refresh(
                repo.url,
                etag=etag,
                last_snapshot_hash=manifest_hash(data),
            )
        if trust_result == "verified":
            self._apply_revocations(validated)
        return True, validated

    def _fetch_manifest_with_mirrors(
        self, repo: SourceRepoEntry, cache_key: str
    ) -> tuple[dict | None, str]:
        data, etag = self._fetch_manifest(repo.url, cache_key, repo.etag)
        if data is not None:
            return data, etag
        cached = self._read_validated_cache(cache_key)
        if not cached:
            return None, ""
        for mirror in cached.get("mirrors", []):
            if not isinstance(mirror, dict):
                continue
            url = str(mirror.get("url") or "")
            if not url.startswith(("http://", "https://")) or url == repo.url:
                continue
            data, etag = self._fetch_manifest(url, cache_key, repo.etag)
            if data is not None:
                log_info(f"[RepoManifest] 主地址失败，镜像命中: {redact_url(url)}")
                return data, etag
        return None, ""

    def _fetch_manifest(
        self, url: str, cache_key: str = "", etag: str = ""
    ) -> tuple[dict | None, str]:
        # 支持 file:// 协议读取本地文件（内置 fallback manifest）
        if url.startswith("file://"):
            return self._fetch_local_manifest(url), ""
        headers = {"If-None-Match": etag} if etag else {}
        try:
            response = self._client.get(url, headers=headers)
            if response.status_code == 304:
                if cache_key:
                    self._touch_cache(cache_key)
                    return self._read_cache(cache_key), ""
                return None, ""
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            log_warning(f"[RepoManifest] HTTP 请求失败: {redact_url(url)} — {e}")
            return None, ""
        except (ValueError, TypeError, OSError) as e:
            log_warning(f"[RepoManifest] 响应解析失败: {redact_url(url)} — {e}")
            return None, ""
        return (data if isinstance(data, dict) else None), str(
            response.headers.get("etag", "")
        )

    @staticmethod
    def _fetch_local_manifest(url: str) -> dict | None:
        """从 file:// URL 读取本地 manifest。"""
        try:
            path = local_path_from_file_uri(url)
            if not path.exists():
                log_warning(f"[RepoManifest] 本地文件不存在: {path}")
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as e:
            log_warning(f"[RepoManifest] 本地文件读取失败: {redact_url(url)} — {e}")
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
            replacement = base_dir.as_posix()
            if not replacement.startswith("/"):
                replacement = "/" + replacement
            str_data = str_data.replace("__BUILTIN_DIR__", replacement)
            return json.loads(str_data)
        return result

    def _maybe_refresh(self, cache_key: str, repo: SourceRepoEntry) -> None:
        lock = self._acquire_refresh_lock(cache_key)
        if lock is None:
            return

        def refresh() -> None:
            try:
                data, etag = self._fetch_manifest_with_mirrors(repo, cache_key)
                if data is not None:
                    accepted, _ = self._accept_manifest(cache_key, repo, data, etag)
                    if accepted:
                        log_info(f"[RepoManifest] 后台刷新成功: {redact_url(repo.url)}")
                    else:
                        log_warning(
                            f"[RepoManifest] 后台刷新被拒(校验/过期/回滚)，保留旧缓存: "
                            f"{redact_url(repo.url)}"
                        )
                else:
                    log_warning(
                        f"[RepoManifest] 后台刷新网络失败: {redact_url(repo.url)}"
                    )
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

    def _read_validated_cache(self, cache_key: str) -> dict | None:
        """读缓存并归一化；校验失败视为无缓存（返回 None）。

        缓存存储网络原始内容（与生产方签名/快照链口径一致），所有对外
        消费点必须经此归一化后再使用。
        """
        cached = self._read_cache(cache_key)
        if cached is None:
            return None
        return validate_repo_manifest(cached)

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

    def _touch_cache(self, cache_key: str) -> None:
        path = self.cache_path(cache_key)
        try:
            if path.exists():
                now = time.time()
                os.utime(path, (now, now))
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

    @staticmethod
    def _manifest_expired(manifest: dict) -> bool:
        """TUF-lite（ADR-011 Phase 3.6）：manifest 自身 expires_at 是否已过。

        语义：缺失 expires_at → 无过期（老 manifest 兼容）；ISO8601 解析失败
        → 视为无过期（不崩溃、不硬失败）；无时区的时间按 UTC 解释。
        """
        raw = str(manifest.get("expires_at") or "").strip()
        if not raw:
            return False
        try:
            expires = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires

    def _check_snapshot_rollback(
        self, cache_key: str, repo: SourceRepoEntry, incoming: dict
    ) -> bool:
        """TUF-lite 防回滚检查：incoming.snapshot_hash 必须等于当前已接受
        manifest 的 hash（链式设计）。

        返回 True = 回滚检测（调用方拒绝替换缓存）。任一缺失（incoming 无
        snapshot_hash，或尚无参照 = 首次拉取）→ 不检查（可选语义）。
        """
        incoming_hash = str(incoming.get("snapshot_hash") or "").strip()
        if not incoming_hash:
            return False
        reference = self._snapshot_reference_hash(cache_key, repo)
        if not reference:
            return False
        return _normalize_snapshot_hash(incoming_hash) != _normalize_snapshot_hash(
            reference
        )

    def _snapshot_reference_hash(self, cache_key: str, repo: SourceRepoEntry) -> str:
        """当前已接受 manifest 的 hash（防回滚参照）。

        优先 repo.last_snapshot_hash（持久化，跨缓存清空存活）；为空且缓存
        存在时从缓存回填计算（升级兼容：老缓存无该字段）。两者皆空 → 无参照。
        """
        if repo.last_snapshot_hash:
            return repo.last_snapshot_hash
        cached = self._read_cache(cache_key)
        if cached is not None:
            return manifest_hash(cached)
        return ""

    def _apply_revocations(self, manifest: dict) -> None:
        """ADR-011 Phase 2.7：把 manifest revocations[] 的 content_hash
        并入本地屏蔽清单（add_blocked_content_hash 去重 + 持久化）。"""
        if self._runtime_config is None:
            return
        for entry in manifest.get("revocations", []):
            if isinstance(entry, dict):
                ch = entry.get("content_hash")
                if isinstance(ch, str) and ch:
                    self._runtime_config.add_blocked_content_hash(ch)

    @staticmethod
    def _manifest_revokes_pubkey(manifest: dict, pubkey: str) -> bool:
        """ADR-011 Phase 2.7：manifest 是否声明撤销自身公钥（key 级撤销）。

        单公钥模型：revocations[] 中 pubkey 与 manifest 自身 trust.pubkey
        相等即视为"该 key 不再可信" → 信任降级，等待用户重新确认。
        """
        if not pubkey:
            return False
        for entry in manifest.get("revocations", []):
            if isinstance(entry, dict) and entry.get("pubkey") == pubkey:
                return True
        return False

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

    def _verify_trust(self, manifest: dict, repo: SourceRepoEntry) -> str:
        """校验 manifest 签名并更新 repo.trust_state（TOFU），返回信任判定。

        ADR-011 决策 12：TOFU 首次信任必须 UI 显式确认。签名有效但
        未固定公钥（首次）或公钥发生变更时，进入 pending 状态等待用户
        确认/拒绝，不再自动 verified；pending 在刷新间保持粘性。

        manifest 必须是网络原始 dict（未归一化）——签名 canonical 以
        生产方签发的原始字节为准，归一化重构会改变字节导致误判。

        返回判定（_accept_manifest 据此决定是否替换缓存）：
        - "verified"：签名有效且固定公钥匹配（已确认）
        - "unverified"：无签名信息（老仓库兼容，接受但不应用 revocations）
        - "pending_new_key" / "pending_changed_key" / "pending_revoked" /
          "pending"：待用户确认（一律拒绝替换缓存）
        - "failed"：签名无效或校验异常（拒绝替换缓存）
        """
        if self._runtime_config is None:
            return "unverified"
        trust = manifest.get("trust") or {}
        signature = trust.get("signature", "")
        pubkey = trust.get("pubkey", "")

        if not signature or not pubkey:
            # 无签名信息 → 未验证
            self._runtime_config.set_source_repo_trust(repo.url, "unverified")
            return "unverified"

        try:
            valid = self._verify_ed25519_signature(manifest, pubkey, signature)
        except Exception as e:
            log_warning(f"[RepoManifest] 签名校验异常: {redact_url(repo.url)} — {e}")
            self._runtime_config.set_source_repo_trust(repo.url, "failed")
            return "failed"

        if not valid:
            self._runtime_config.set_source_repo_trust(repo.url, "failed")
            return "failed"

        # ADR-011 Phase 2.7：manifest 声明撤销自身公钥 → 信任降级 pending，
        # 用户重新确认/拒绝（决策 12）。签名仍须有效：撤销声明是已签名内容
        # 的一部分，防伪造降级攻击。固定公钥保留，仓库停发撤销声明后下一轮
        # 刷新即恢复正常；key 实际轮换时走下方 pin 变更路径。
        if self._manifest_revokes_pubkey(manifest, pubkey):
            self._runtime_config.set_source_repo_trust(
                repo.url, "pending", pinned_pubkey=pubkey
            )
            log_warning(
                f"[RepoManifest] 仓库公钥被自身撤销，信任降级待确认: "
                f"{redact_url(repo.url)}"
            )
            return "pending_revoked"

        if not repo.pinned_pubkey:
            # 首次有效签名：固定公钥，进入 pending，等待用户 UI 确认
            self._runtime_config.set_source_repo_trust(
                repo.url, "pending", pinned_pubkey=pubkey
            )
            log_info(f"[RepoManifest] 首次有效签名，待用户确认: {redact_url(repo.url)}")
            return "pending_new_key"
        elif repo.pinned_pubkey != pubkey:
            # 公钥变更 → 回到 pending（固定新公钥），需用户重新确认/拒绝
            self._runtime_config.set_source_repo_trust(
                repo.url, "pending", pinned_pubkey=pubkey
            )
            log_warning(f"[RepoManifest] 公钥变更，待用户确认: {redact_url(repo.url)}")
            return "pending_changed_key"
        elif repo.trust_state == "pending":
            # pending 粘性：刷新保持 pending，等待用户操作后再转 verified
            return "pending"
        else:
            self._runtime_config.set_source_repo_trust(repo.url, "verified")
            return "verified"

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
            key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            key.verify(sig_bytes, canonical_bytes)
            return True
        except (InvalidSignature, ValueError):
            return False
