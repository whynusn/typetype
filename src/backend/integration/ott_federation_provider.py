"""OTT 联邦目录聚合层（OTT Repo 控制面）。

职责：
- 从所有已启用订阅的 Repo Manifest 中提取 ott-instance / ott-rule 源
- 为每个 instance 建立按 authority 命名的客户端（按 endpoint priority + 健康度 failover）
- 为每个 rule 建立 _RuleClient（调用 L1 解释器执行声明式规则）
- 聚合所有 instance + rule 的 entries，按 authority 命名空间隔离
- 按 authority 路由 entry detail / segment 请求到对应客户端

明确不做：
- 不重复实现 OTT Core v1 协议细节（由 OttClient 承载）
- 不替换现有单实例 OttTextProvider（向后兼容，旧路径仍可用）
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ..config.runtime_config import RuntimeConfig, SourceRepoEntry
from ..utils.logger import log_info, log_warning
from .ott_cached_fetcher import OttCachedFetcher
from .ott_normalization import _bridge_authority, _script_authority, redact_url
from .ott_client import DEFAULT_STATIC_SEGMENT_SIZE, OttClient, FetchJson, FetchText
from .ott_repo_manifest import RepoManifestCache, repo_cache_key
from .ott_rule_interpreter import CLIENT_API_LEVEL, OttRuleInterpreter
from .ott_script_client import ScriptCache, ScriptSandbox

if TYPE_CHECKING:
    from ..ports.async_executor import AsyncExecutor
    from ..ports.token_store import TokenStore


CLIENT_OTT_CORE_VERSION = "1.0"
CLIENT_FEATURES = frozenset({"entry_summary", "inline_content", "segmented_content"})
_VERSION_CONSTRAINT_RE = re.compile(r"^(>=|<=|>|<|==|=)?\s*(\d+(?:\.\d+)*)$")
_VERSION_OPERATIONS: dict[str, Callable[[int], bool]] = {
    "": lambda c: c == 0,
    "=": lambda c: c == 0,
    "==": lambda c: c == 0,
    ">": lambda c: c > 0,
    ">=": lambda c: c >= 0,
    "<": lambda c: c < 0,
    "<=": lambda c: c <= 0,
}


def _compare_versions(a: str, b: str) -> int:
    a_parts = tuple(int(p) for p in a.split("."))
    b_parts = tuple(int(p) for p in b.split("."))
    if a_parts > b_parts:
        return 1
    if a_parts < b_parts:
        return -1
    return 0


def _satisfies_ott_core(constraint: str, version: str) -> bool:
    match = _VERSION_CONSTRAINT_RE.match(constraint.strip())
    if match is None:
        return False
    op, required = match.groups()
    cmp_result = _compare_versions(version, required)
    return _VERSION_OPERATIONS[op or ""](cmp_result)


def _repo_incompatibility(manifest: dict) -> str | None:
    requires = manifest.get("requires")
    if not isinstance(requires, dict):
        return None
    ott_core = requires.get("ott_core")
    if (
        isinstance(ott_core, str)
        and ott_core
        and not _satisfies_ott_core(ott_core, CLIENT_OTT_CORE_VERSION)
    ):
        return f"需要 OTT Core {ott_core}，客户端为 {CLIENT_OTT_CORE_VERSION}"
    features = requires.get("client_features")
    if isinstance(features, list):
        missing = sorted(
            f for f in features if isinstance(f, str) and f and f not in CLIENT_FEATURES
        )
        if missing:
            return f"缺少客户端能力: {', '.join(missing)}"
    return None


class _EntryCache:
    """rule/script 条目结果 TTL 缓存（复用 ott.cache_ttl_seconds）。"""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = max(1, ttl_seconds)
        self._items: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> list[dict] | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            timestamp, entries = item
            if time.time() - timestamp > self._ttl_seconds:
                self._items.pop(key, None)
                return None
            return entries

    def set(self, key: str, entries: list[dict]) -> None:
        with self._lock:
            self._items[key] = (time.time(), entries)


class _InstanceClient:
    """单个 ott-instance 的客户端封装。

    endpoints 按 priority 排序；健康度用近期失败次数做指数退避，
    连续失败的端点排在健康端点之后。
    """

    def __init__(
        self,
        authority: str,
        endpoints: list[dict],
        cache: OttCachedFetcher,
        max_content_bytes: int,
    ) -> None:
        self.authority = authority
        self._endpoints = sorted(endpoints, key=lambda e: e.get("priority", 1))
        self._cache = cache
        self._max_content_bytes = max_content_bytes
        self._failure_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _ordered_urls(self) -> list[str]:
        """按健康度排序的端点 URL：健康端点优先，同健康度按 priority。"""
        with self._lock:
            pairs = []
            for ep in self._endpoints:
                url = ep.get("url", "")
                if not url:
                    continue
                fails = self._failure_counts.get(url, 0)
                pairs.append((fails, ep.get("priority", 1), url))
        pairs.sort(key=lambda x: (x[0], x[1]))
        return [p[2] for p in pairs]

    def _record_success(self, url: str) -> None:
        with self._lock:
            self._failure_counts.pop(url, None)

    def _record_failure(self, url: str) -> None:
        with self._lock:
            self._failure_counts[url] = self._failure_counts.get(url, 0) + 1

    def _make_fetch_json(self) -> FetchJson:
        def fetch(
            cache_key: str, fetch_url: str, mirror_url: str | None, max_bytes: int
        ) -> dict | None:
            return self._cache.fetch_json_with_cache(
                cache_key, fetch_url, mirror_url, max_bytes
            )

        return fetch

    def _make_fetch_text(self) -> FetchText:
        def fetch(
            cache_key: str, fetch_url: str, mirror_url: str | None, max_bytes: int
        ) -> str | None:
            return self._cache.fetch_text_with_cache(
                cache_key, fetch_url, mirror_url, max_bytes
            )

        return fetch

    def _client_for(self, url: str) -> OttClient:
        return OttClient(
            primary_url=url,
            mirror_url="",
            authority=self.authority,
            fetch_json=self._make_fetch_json(),
            fetch_text=self._make_fetch_text(),
            max_content_bytes=self._max_content_bytes,
        )

    def list_entries(self) -> list[dict] | None:
        for url in self._ordered_urls():
            client = self._client_for(url)
            try:
                entries = client.list_entries()
            except Exception as e:
                log_warning(
                    f"[Federation] list_entries 异常 {self.authority}@{redact_url(url)}: {e}"
                )
                self._record_failure(url)
                continue
            if entries is not None:
                self._record_success(url)
                return entries
            self._record_failure(url)
        return None

    def list_sources(self) -> list[dict] | None:
        for url in self._ordered_urls():
            client = self._client_for(url)
            try:
                sources = client.list_sources()
            except Exception as e:
                log_warning(
                    f"[Federation] list_sources 异常 {self.authority}@{redact_url(url)}: {e}"
                )
                self._record_failure(url)
                continue
            if sources is not None:
                self._record_success(url)
                return sources
            self._record_failure(url)
        return None

    def get_entry(self, entry_id: str) -> dict | None:
        for url in self._ordered_urls():
            client = self._client_for(url)
            try:
                detail = client.get_entry(entry_id)
            except Exception as e:
                log_warning(
                    f"[Federation] get_entry 异常 {self.authority}@{redact_url(url)}: {e}"
                )
                self._record_failure(url)
                continue
            if detail is not None:
                self._record_success(url)
                return detail
            self._record_failure(url)
        return None

    def get_segment(
        self,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size: int = 1000,
    ) -> dict | None:
        for url in self._ordered_urls():
            client = self._client_for(url)
            try:
                seg = client.get_segment(
                    entry_id,
                    revision_id,
                    segment_index,
                    segment_size,
                )
            except Exception as e:
                log_warning(
                    f"[Federation] get_segment 异常 {self.authority}@{redact_url(url)}: {e}"
                )
                self._record_failure(url)
                continue
            if seg is not None:
                self._record_success(url)
                return seg
            self._record_failure(url)
        return None


class _SourceClientBase:
    """_RuleClient / _ScriptClient 公共实现：按 entry_id 查询与内容分段。

    list_entries 由子类实现；get_entry / get_segment 基于其输出工作。
    """

    def get_entry(self, entry_id: str) -> dict | None:
        """按 entry_id 从客户端产出中查找单条。"""
        entries = self.list_entries()
        if entries is None:
            return None
        for e in entries:
            if e.get("entry_id") == entry_id:
                return e
        return None

    def get_segment(
        self,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size: int = DEFAULT_STATIC_SEGMENT_SIZE,
    ) -> dict | None:
        """获取单条 entry 的内容分段（客户端本地切片）。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None
        content = entry.get("content", "")
        if not content:
            return None
        seg_size = max(1, segment_size)
        start = (segment_index - 1) * seg_size
        end = start + seg_size
        segment_content = content[start:end]
        if not segment_content:
            return None
        return {
            "entry_id": entry_id,
            "revision_id": revision_id,
            "index": segment_index,
            "start_char": start,
            "end_char": start + len(segment_content),
            "char_count": len(segment_content),
            "content_hash": "sha256:"
            + hashlib.sha256(segment_content.encode("utf-8")).hexdigest(),
            "content": segment_content,
            "total_chars": len(content),
        }


class _RuleClient(_SourceClientBase):
    """单个 ott-rule 的客户端封装。

    调用 L1 解释器执行声明式规则，产出标准化 entry 列表。
    authority = ``rule:{repo_id}:{rule_id}``（repo_id 为空时回退
    ``rule:{rule_id}``），与 ott-instance 命名空间隔离。
    """

    def __init__(
        self,
        rule_id: str,
        rule: dict,
        interpreter: OttRuleInterpreter,
        authority: str = "",
        entry_cache: _EntryCache | None = None,
    ) -> None:
        self.rule_id = rule_id
        self._rule = rule
        self._interpreter = interpreter
        self._entry_cache = entry_cache
        # authority 格式：rule:{repo_id}:{rule_id}（上游规范）
        self.authority = authority or f"rule:{rule_id}"

    def list_entries(self) -> list[dict] | None:
        cache_key = f"rule:{self.authority}"
        cached = self._entry_cache.get(cache_key) if self._entry_cache else None
        if cached is not None:
            return cached
        try:
            # 契约 C2：非空 authority 时解释器负责 entry 的 authority/source_key，
            # 客户端不再事后补丁
            entries = self._interpreter.list_entries(
                self._rule, self.rule_id, authority=self.authority
            )
        except Exception as e:
            log_warning(f"[Federation] rule 执行异常 {self.rule_id}: {e}")
            return None
        if not entries:
            return []
        if self._entry_cache is not None:
            self._entry_cache.set(cache_key, entries)
        return entries


class _ScriptClient(_SourceClientBase):
    """单个 ott-script 的客户端封装。

    下载脚本 → AST 安全检查 → 沙箱执行 → 产出标准化 entry 列表。
    authority = ``script:{sha256(url)[:12]}``（按 URL 指纹隔离）。
    secret_names 来自 manifest 的 permissions.secrets 声明（信任边界）：
    仅声明的凭据名会传给 ScriptSandbox 注入，脚本无法自行请求任意凭据。
    checksum 来自 manifest source 的 checksum 字段，非空时按契约 C1
    交给 ScriptCache 校验脚本字节 sha256。
    """

    def __init__(
        self,
        url: str,
        label: str,
        script_cache: ScriptCache,
        sandbox: ScriptSandbox,
        entry_cache: _EntryCache | None = None,
        secret_names: list[str] | None = None,
        network_allowlist: list[str] | None = None,
        min_api_level: int | None = None,
        checksum: str = "",
    ) -> None:
        self.url = url
        self.label = label
        self.authority = _script_authority(url)
        self._cache = script_cache
        self._sandbox = sandbox
        self._entry_cache = entry_cache
        self._secret_names = list(secret_names) if secret_names else []
        self._network_allowlist = list(network_allowlist) if network_allowlist else []
        self._min_api_level = min_api_level
        self._checksum = checksum

    def list_entries(self) -> list[dict] | None:
        cache_key = f"script:{self.url}"
        cached = self._entry_cache.get(cache_key) if self._entry_cache else None
        if cached is not None:
            return cached
        # 契约 C1：checksum 非空时交给 ScriptCache 校验脚本字节 sha256
        if self._checksum:
            source = self._cache.get_script(self.url, expected_checksum=self._checksum)
        else:
            source = self._cache.get_script(self.url)
        if source is None:
            log_warning(f"[Federation] script 下载失败: {redact_url(self.url)}")
            return None
        try:
            entries = self._sandbox.execute(
                source,
                self.url,
                secret_names=self._secret_names or None,
                network_allowlist=self._network_allowlist or None,
                min_api_level=self._min_api_level,
            )
        except Exception as e:
            log_warning(f"[Federation] script 执行异常 {redact_url(self.url)}: {e}")
            return None
        if not entries:
            return []
        for e in entries:
            e["authority"] = self.authority
            e["_authority"] = self.authority
            e["source_label"] = self.label or e.get("source_label", "脚本源")
        if self._entry_cache is not None:
            self._entry_cache.set(cache_key, entries)
        return entries


class _BridgeClient(_SourceClientBase):
    """单个 ott-bridge 的客户端封装。

    首个内置桥协议为 ``generic-http``（无凭据 GET endpoint → JSON entry）。
    对 endpoint 发 GET 请求，按协议契约解析响应为标准化 entry 列表。
    authority = ``bridge:{sha256(endpoint)[:12]}``（endpoint 指纹隔离）。
    未知 bridge_kind / 需凭据的桥按协议契约跳过（客户端不应猜测 wire format）。
    """

    def __init__(
        self,
        bridge_kind: str,
        endpoint: str,
        label: str,
        http_client: httpx.Client,
        entry_cache: _EntryCache | None = None,
        max_content_bytes: int = 0,
    ) -> None:
        self.bridge_kind = bridge_kind
        self.endpoint = endpoint
        self.label = label
        self.authority = _bridge_authority(endpoint)
        self._http_client = http_client
        self._entry_cache = entry_cache
        self._max_content_bytes = max_content_bytes

    def list_entries(self) -> list[dict] | None:
        if self.bridge_kind != "generic-http":
            log_warning(
                f"[Federation] bridge_kind {self.bridge_kind!r} 未实现，跳过: "
                f"{redact_url(self.endpoint)}"
            )
            return None
        cache_key = f"bridge:{self.authority}"
        cached = self._entry_cache.get(cache_key) if self._entry_cache else None
        if cached is not None:
            return cached
        try:
            data = self._fetch_generic_http()
        except Exception as e:
            log_warning(f"[Federation] bridge 请求异常 {self.authority}: {e}")
            return None
        entries = self._normalize_bridge_response(data)
        if not entries:
            return []
        for e in entries:
            e["authority"] = self.authority
            e["_authority"] = self.authority
            e["source_label"] = self.label or e.get("source_label", "桥接源")
        if self._entry_cache is not None:
            self._entry_cache.set(cache_key, entries)
        return entries

    def _fetch_generic_http(self) -> Any:
        """GET endpoint 并返回解析后的 JSON 数据。

        仅 http(s) endpoint；响应 JSON 需为 object（单条或 {"entries": [...]}）。
        """
        url = self.endpoint
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError(f"非 http(s) bridge endpoint: {redact_url(url)}")
        resp = self._http_client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("generic-http 响应必须是 JSON object")
        return data

    def _normalize_bridge_response(self, data: dict) -> list[dict]:
        """按 generic-http 契约把响应归一化为 entry 列表。

        单条：{title, content, ...}；列表：{"entries": [{...}, ...]}。
        entry_id 缺省时从 content hash 派生稳定 id（重复内容去重）。
        """
        if isinstance(data.get("entries"), list):
            raw_items = data["entries"]
        else:
            raw_items = [data]
        entries: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            content = content.strip()
            if self._max_content_bytes:
                # 按 UTF-8 字节数安全截断（避免切片落在多字节字符中间）
                encoded = content.encode("utf-8")
                if len(encoded) > self._max_content_bytes:
                    content = encoded[: self._max_content_bytes].decode(
                        "utf-8", errors="ignore"
                    )
            entry_id = str(item.get("entry_id") or "") or (
                "bridge:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            )
            entries.append(
                {
                    "entry_id": entry_id,
                    "title": str(item.get("title") or "") or "桥接文本",
                    "content": content,
                    "preview": str(item.get("preview") or "") or content[:80],
                    "source_key": str(item.get("source_key") or "") or "bridge",
                    "char_count": len(content),
                    "content_mode": "inline",
                    "current_revision_id": "v1",
                    "tags": item.get("tags")
                    if isinstance(item.get("tags"), list)
                    else [],
                    "category": str(item.get("category") or "") or "",
                }
            )
        return entries


def _declared_script_secrets(source: dict) -> list[str]:
    """提取 manifest 脚本源声明的 permissions.secrets（容错，缺省为空）。

    信任边界：仅 manifest 声明的凭据名会传给沙箱，脚本无法自行请求任意凭据。
    """
    permissions = source.get("permissions")
    if not isinstance(permissions, dict):
        return []
    raw = permissions.get("secrets")
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, str) and s]


def _declared_script_network(source: dict) -> list[str]:
    """提取 manifest 脚本源声明的 permissions.network 域名白名单（容错，缺省为空）。

    空 → 沙箱内一切 http(s) 请求被拒（deny-by-default）。
    """
    permissions = source.get("permissions")
    if not isinstance(permissions, dict):
        return []
    raw = permissions.get("network")
    if not isinstance(raw, list):
        return []
    return [h for h in raw if isinstance(h, str) and h.strip()]


def _declared_script_api_level(source: dict) -> int | None:
    """提取 manifest 脚本源声明的 rights.min_api_level（容错，缺省 None）。

    None → 无版本门槛；高于客户端 CLIENT_API_LEVEL 的脚本被跳过。
    """
    rights = source.get("rights")
    if not isinstance(rights, dict):
        return None
    level = rights.get("min_api_level")
    if isinstance(level, int) and not isinstance(level, bool) and level > 0:
        return level
    return None


class OttFederationProvider:
    """OTT 联邦目录聚合层。

    聚合所有已启用订阅中的 ott-instance 源，按 authority 命名空间
    隔离条目，提供统一查询入口。
    """

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        manifest_cache: RepoManifestCache,
        max_content_bytes: int = 1_048_576,
        token_store: TokenStore | None = None,
        async_executor: AsyncExecutor | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._manifest_cache = manifest_cache
        self._max_content_bytes = max_content_bytes
        self._token_store = token_store
        self._async_executor = async_executor
        if async_executor is None:
            log_warning(
                "[Federation] 未注入 async_executor，instance 缓存 stale 刷新禁用"
            )
        self._entry_cache = _EntryCache(runtime_config.ott.cache_ttl_seconds)
        self._clients_cache: (
            dict[str, _InstanceClient | _RuleClient | _ScriptClient] | None
        ) = None
        self._clients_cache_signature: tuple[object, ...] | None = None
        self._shared_client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # 内部：从 manifest 构建 authority → _InstanceClient 映射
    # ------------------------------------------------------------------

    def _build_clients(
        self,
    ) -> dict[str, _InstanceClient | _RuleClient | _ScriptClient | _BridgeClient]:
        """遍历所有已启用订阅，提取 ott-instance / ott-rule / ott-bridge / ott-script，按 authority 建客户端。"""
        signature = self._clients_signature()
        if (
            self._clients_cache is not None
            and signature == self._clients_cache_signature
        ):
            return self._clients_cache
        clients: dict[
            str, _InstanceClient | _RuleClient | _ScriptClient | _BridgeClient
        ] = {}
        # 复用同一个解释器/沙箱实例（内部无状态）
        interpreter = OttRuleInterpreter(
            http_client=self._shared_http_client(),
            max_bytes=self._max_content_bytes,
            api_level=CLIENT_API_LEVEL,
        )
        script_cache = ScriptCache(
            cache_dir=self._script_cache_dir(),
            http_client=self._shared_http_client(),
            enabled=self._runtime_config.ott.scripts_enabled,
            ttl_seconds=self._runtime_config.ott.cache_ttl_seconds,
        )
        sandbox = ScriptSandbox(
            enabled=self._runtime_config.ott.scripts_enabled,
            token_store=self._token_store,
        )

        for repo in self._runtime_config.source_repos.enabled_repos:
            manifest = self._manifest_for(repo)
            if manifest is None:
                continue
            reason = _repo_incompatibility(manifest)
            if reason is not None:
                log_warning(
                    f"[Federation] 仓库不兼容跳过: {redact_url(repo.url)} — {reason}"
                )
                continue
            repo_id = manifest.get("repo_id", "")
            for source in manifest.get("sources", []):
                if not source.get("default_enabled", True):
                    continue
                source_type = source.get("type")
                if source_type == "ott-instance":
                    self._build_instance_client(clients, source)
                elif source_type == "ott-rule":
                    self._build_rule_client(
                        clients, source, interpreter, repo_id, self._entry_cache
                    )
                elif source_type == "ott-script":
                    if repo.trust_state != "verified":
                        log_warning(
                            f"[Federation] 仓库未验证，跳过 L3 脚本: "
                            f"{redact_url(repo.url)}"
                        )
                        continue
                    self._build_script_client(
                        clients,
                        source,
                        script_cache,
                        sandbox,
                        self._entry_cache,
                    )
                elif source_type == "ott-bridge":
                    self._build_bridge_client(
                        clients,
                        source,
                        self._shared_http_client(),
                        self._entry_cache,
                    )
        self._clients_cache = clients
        self._clients_cache_signature = self._clients_signature()
        return clients

    def _shared_http_client(self) -> httpx.Client:
        if self._shared_client is None:
            self._shared_client = httpx.Client(
                timeout=10.0, trust_env=False, follow_redirects=False
            )
        return self._shared_client

    def close(self) -> None:
        """关闭共享 HTTP client（幂等；从未创建时安全无操作）。"""
        if self._shared_client is not None:
            self._shared_client.close()
            self._shared_client = None

    def _clients_signature(self) -> tuple[object, ...]:
        signature: list[object] = []
        for repo in self._runtime_config.source_repos.repos:
            mtime = 0.0
            try:
                mtime = (
                    self._manifest_cache.cache_path(repo_cache_key(repo.url))
                    .stat()
                    .st_mtime
                )
            except OSError:
                pass
            # trust_state 必须入签名：仓库从 verified 降级为 pending（公钥轮换 /
            # revocations）时，即使 url/enabled/mtime 不变也要触发 clients 重建，
            # 否则旧 _ScriptClient（含 L3 脚本执行能力）会被继续复用。
            signature.append((repo.url, repo.enabled, repo.trust_state, mtime))
        signature.append(self._runtime_config.ott.scripts_enabled)
        return tuple(signature)

    def _blocked_content_hashes(self) -> set[str]:
        raw = getattr(self._runtime_config, "blocked_content_hashes", None)
        if not isinstance(raw, list):
            return set()
        return {h for h in raw if isinstance(h, str) and h}

    def _manifest_for(self, repo: SourceRepoEntry) -> dict | None:
        """本地内置订阅直读 manifest，远程订阅走缓存。"""
        if repo.url.startswith("file://"):
            return self._manifest_cache.load_local_manifest(repo)
        return self._manifest_cache.get_manifest(repo)

    def _script_cache_dir(self) -> Path:
        from ..config.app_paths import registry_cache_dir

        return registry_cache_dir() / "scripts"

    def _build_instance_client(
        self,
        clients: dict[str, _InstanceClient | _RuleClient | _ScriptClient],
        source: dict,
    ) -> None:
        authority = source.get("authority", "")
        endpoints = source.get("endpoints", [])
        if not authority or not endpoints:
            return
        existing = clients.get(authority)
        if existing:
            if not isinstance(existing, _InstanceClient):
                return  # authority 类型冲突，跳过
            seen = {e.get("url") for e in existing._endpoints}
            for ep in endpoints:
                if ep.get("url") not in seen:
                    existing._endpoints.append(ep)
            existing._endpoints.sort(key=lambda e: e.get("priority", 1))
            return
        cache_dir = self._instance_cache_dir(authority)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = OttCachedFetcher(
            config=self._runtime_config.ott,
            cache_dir=cache_dir,
            http_client=self._shared_http_client(),
            async_executor=self._async_executor,
        )
        clients[authority] = _InstanceClient(
            authority=authority,
            endpoints=endpoints,
            cache=cache,
            max_content_bytes=self._max_content_bytes,
        )

    @staticmethod
    def _build_rule_client(
        clients: dict[str, _InstanceClient | _RuleClient | _ScriptClient],
        source: dict,
        interpreter: OttRuleInterpreter,
        repo_id: str = "",
        entry_cache: _EntryCache | None = None,
    ) -> None:
        rule_id = source.get("rule_id", "")
        rule = source.get("rule")
        if not rule_id or not isinstance(rule, dict):
            return
        # 上游规范：rule:{repo_id}:{rule_id}（含 repo_id 命名空间，防跨 repo 冲突）
        authority = f"rule:{repo_id}:{rule_id}" if repo_id else f"rule:{rule_id}"
        if authority in clients:
            return  # 同名 rule 已存在
        clients[authority] = _RuleClient(
            rule_id=rule_id,
            rule=rule,
            interpreter=interpreter,
            authority=authority,
            entry_cache=entry_cache,
        )

    @staticmethod
    def _build_script_client(
        clients: dict[str, _InstanceClient | _RuleClient | _ScriptClient],
        source: dict,
        script_cache: ScriptCache,
        sandbox: ScriptSandbox,
        entry_cache: _EntryCache | None = None,
    ) -> None:
        url = source.get("url", "")
        if not url:
            return
        label = source.get("label", "")
        # 用 URL 指纹作 authority key（避免重复下载同脚本，防跨脚本 entry_id 冲突）
        key = _script_authority(url)
        if key in clients:
            return
        clients[key] = _ScriptClient(
            url=url,
            label=label,
            script_cache=script_cache,
            sandbox=sandbox,
            entry_cache=entry_cache,
            secret_names=_declared_script_secrets(source),
            network_allowlist=_declared_script_network(source),
            min_api_level=_declared_script_api_level(source),
            checksum=source.get("checksum", ""),
        )

    @staticmethod
    def _build_bridge_client(
        clients: dict[
            str, _InstanceClient | _RuleClient | _ScriptClient | _BridgeClient
        ],
        source: dict,
        http_client: httpx.Client,
        entry_cache: _EntryCache | None = None,
    ) -> None:
        bridge_kind = source.get("bridge_kind", "")
        endpoint = source.get("endpoint", "")
        if not bridge_kind or not endpoint:
            return
        label = source.get("label", "")
        # 用 endpoint 指纹作 authority key（防跨 bridge 源 entry_id 冲突）
        key = _bridge_authority(endpoint)
        if key in clients:
            return
        clients[key] = _BridgeClient(
            bridge_kind=bridge_kind,
            endpoint=endpoint,
            label=label,
            http_client=http_client,
            entry_cache=entry_cache,
        )

    def _instance_cache_dir(self, authority: str) -> Path:
        from ..config.app_paths import registry_cache_dir

        suffix = hashlib.sha256(authority.encode("utf-8")).hexdigest()[:12]
        return registry_cache_dir() / "instances" / suffix

    # ------------------------------------------------------------------
    # 公共查询接口
    # ------------------------------------------------------------------

    def list_all_entries(self) -> list[dict]:
        """聚合所有 instance 的条目列表，按 authority 命名空间隔离。"""
        clients = self._build_clients()
        if not clients:
            return []
        all_entries: list[dict] = []
        for authority, client in clients.items():
            log_info(
                f"[Federation] listing entries for {authority} ({type(client).__name__})"
            )
            try:
                entries = client.list_entries()
            except Exception as e:
                log_warning(f"[Federation] list_entries 异常 {authority}: {e}")
                continue
            log_info(
                f"[Federation] {authority}: {len(entries) if entries else 0} entries"
            )
            if entries:
                for e in entries:
                    if isinstance(e, dict):
                        e["_authority"] = authority
                        if not e.get("authority"):
                            e["authority"] = authority
                all_entries.extend(entries)
        seen: dict[str, dict] = {}
        blocked = self._blocked_content_hashes()
        for e in all_entries:
            if e.get("content_hash") in blocked:
                continue
            key = f"{e.get('_authority', '')}:{e.get('entry_id', '')}"
            if key in seen:
                continue
            seen[key] = e
        return list(seen.values())

    def get_entry(self, authority: str, entry_id: str) -> dict | None:
        clients = self._build_clients()
        client = clients.get(authority)
        if client is None:
            return None
        detail = client.get_entry(entry_id)
        if detail is None:
            return None
        if detail.get("content_hash") in self._blocked_content_hashes():
            return None
        return detail

    def get_segment(
        self,
        authority: str,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size: int = DEFAULT_STATIC_SEGMENT_SIZE,
    ) -> dict | None:
        clients = self._build_clients()
        client = clients.get(authority)
        if client is None:
            return None
        seg = client.get_segment(entry_id, revision_id, segment_index, segment_size)
        if seg is None:
            return None
        # 对齐 get_entry：content_hash 在屏蔽清单 → 视为不存在
        if seg.get("content_hash") in self._blocked_content_hashes():
            return None
        return seg

    def list_repos(self) -> list[dict]:
        """返回订阅及其 manifest 摘要（供 UI 订阅管理使用）。

        disabled 订阅不拉取 manifest（零网络），仅用本地 repo 元数据
        标注 enabled=false。
        """
        result: list[dict] = []
        for repo in self._runtime_config.source_repos.repos:
            if not repo.url:
                continue
            if not repo.enabled:
                result.append(
                    {
                        "url": repo.url,
                        "enabled": False,
                        "trust_state": repo.trust_state,
                        "added_at": repo.added_at,
                        "loaded": False,
                        "name": "",
                        "description": "",
                        "repo_id": "",
                        "authorities": [],
                        "instance_count": 0,
                        "error": None,
                        "incompatible_reason": None,
                        "unsupported_sources": [],
                    }
                )
                continue
            manifest = self._manifest_for(repo)
            reason = _repo_incompatibility(manifest) if manifest else None
            if manifest is not None and reason is not None:
                result.append(
                    {
                        "url": repo.url,
                        "enabled": repo.enabled,
                        "trust_state": repo.trust_state,
                        "added_at": repo.added_at,
                        "loaded": True,
                        "name": manifest.get("name", ""),
                        "description": manifest.get("description", ""),
                        "repo_id": manifest.get("repo_id", ""),
                        "authorities": [],
                        "instance_count": 0,
                        "error": None,
                        "incompatible_reason": reason,
                    }
                )
                continue
            unsupported_sources = [
                str(source.get("label") or source.get("bridge_kind") or "")
                for source in (manifest or {}).get("sources", [])
                if source.get("type") == "ott-bridge"
                and source.get("bridge_kind") != "generic-http"
            ]
            # 收集 manifest 中所有源的 authority
            authorities: list[str] = []
            if manifest:
                for source in manifest.get("sources", []):
                    if source.get("type") == "ott-instance":
                        auth = source.get("authority", "")
                        if auth:
                            authorities.append(auth)
                    elif source.get("type") == "ott-rule":
                        rule_id = source.get("rule_id", "")
                        if rule_id:
                            repo_id = manifest.get("repo_id", "")
                            authorities.append(
                                f"rule:{repo_id}:{rule_id}"
                                if repo_id
                                else f"rule:{rule_id}"
                            )
                    elif source.get("type") == "ott-script":
                        url = source.get("url", "")
                        authorities.append(_script_authority(url) if url else "script")
                    elif source.get("type") == "ott-bridge":
                        endpoint = source.get("endpoint", "")
                        authorities.append(
                            _bridge_authority(endpoint) if endpoint else "bridge"
                        )
            summary = {
                "url": repo.url,
                "enabled": repo.enabled,
                "trust_state": repo.trust_state,
                "added_at": repo.added_at,
                "loaded": manifest is not None,
                "name": manifest.get("name", "") if manifest else "",
                "description": manifest.get("description", "") if manifest else "",
                "repo_id": manifest.get("repo_id", "") if manifest else "",
                "authorities": authorities,
                "instance_count": (
                    sum(
                        1
                        for s in manifest.get("sources", [])
                        if s.get("type") == "ott-instance"
                    )
                    if manifest
                    else 0
                ),
                "error": None if manifest else "加载失败",
                "incompatible_reason": None,
                "unsupported_sources": unsupported_sources,
            }
            result.append(summary)
        return result
