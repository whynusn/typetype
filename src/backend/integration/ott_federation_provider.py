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
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ..config.runtime_config import RuntimeConfig
from ..utils.logger import log_info, log_warning
from .ott_cached_fetcher import OttCachedFetcher
from .ott_normalization import redact_url
from .ott_client import OttClient, FetchJson, FetchText
from .ott_repo_manifest import RepoManifestCache
from .ott_rule_interpreter import CLIENT_API_LEVEL, OttRuleInterpreter
from .ott_script_client import ScriptCache, ScriptSandbox

if TYPE_CHECKING:
    pass


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

    def _make_fetch_json(self, url: str) -> FetchJson:
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
            fetch_json=self._make_fetch_json(url),
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
                    entry_id, revision_id, segment_index, segment_size
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


class _RuleClient:
    """单个 ott-rule 的客户端封装。

    调用 L1 解释器执行声明式规则，产出标准化 entry 列表。
    authority = ``rule:{rule_id}``，与 ott-instance 命名空间隔离。
    """

    def __init__(
        self,
        rule_id: str,
        rule: dict,
        interpreter: OttRuleInterpreter,
        authority: str = "",
    ) -> None:
        self.rule_id = rule_id
        self._rule = rule
        self._interpreter = interpreter
        # authority 格式：rule:{repo_id}:{rule_id}（上游规范）
        self.authority = authority or f"rule:{rule_id}"

    def list_entries(self) -> list[dict] | None:
        try:
            entries = self._interpreter.list_entries(self._rule, self.rule_id)
        except Exception as e:
            log_warning(f"[Federation] rule 执行异常 {self.rule_id}: {e}")
            return None
        if not entries:
            return []
        for e in entries:
            e["authority"] = self.authority
            e["_authority"] = e["authority"]
        return entries

    def get_entry(self, entry_id: str) -> dict | None:
        """按 entry_id 从规则产出中查找单条。"""
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
        segment_size: int = 1000,
    ) -> dict | None:
        """获取规则源单条的内容分段。"""
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


class _ScriptClient:
    """单个 ott-script 的客户端封装。

    下载脚本 → AST 安全检查 → 沙箱执行 → 产出标准化 entry 列表。
    authority = ``script``，与 ott-instance / ott-rule 命名空间隔离。
    """

    def __init__(
        self,
        url: str,
        label: str,
        script_cache: ScriptCache,
        sandbox: ScriptSandbox,
    ) -> None:
        self.url = url
        self.label = label
        self._cache = script_cache
        self._sandbox = sandbox

    def list_entries(self) -> list[dict] | None:
        source = self._cache.get_script(self.url)
        if source is None:
            log_warning(f"[Federation] script 下载失败: {redact_url(self.url)}")
            return None
        try:
            entries = self._sandbox.execute(source, self.url)
        except Exception as e:
            log_warning(f"[Federation] script 执行异常 {redact_url(self.url)}: {e}")
            return None
        if not entries:
            return []
        for e in entries:
            e["authority"] = "script"
            e["_authority"] = "script"
            e["source_label"] = self.label or e.get("source_label", "脚本源")
        return entries

    def get_entry(self, entry_id: str) -> dict | None:
        """按 entry_id 从脚本产出中查找单条。"""
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
        segment_size: int = 1000,
    ) -> dict | None:
        """获取脚本源单条的内容分段。"""
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
    ) -> None:
        self._runtime_config = runtime_config
        self._manifest_cache = manifest_cache
        self._max_content_bytes = max_content_bytes

    # ------------------------------------------------------------------
    # 内部：从 manifest 构建 authority → _InstanceClient 映射
    # ------------------------------------------------------------------

    def _build_clients(
        self,
    ) -> dict[str, _InstanceClient | _RuleClient | _ScriptClient]:
        """遍历所有已启用订阅，提取 ott-instance / ott-rule / ott-script，按 authority 建客户端。"""
        clients: dict[str, _InstanceClient | _RuleClient | _ScriptClient] = {}
        # 复用同一个解释器/沙箱实例（内部无状态）
        interpreter = OttRuleInterpreter(
            http_client=httpx.Client(
                timeout=10.0, trust_env=False, follow_redirects=False
            ),
            max_bytes=self._max_content_bytes,
            api_level=CLIENT_API_LEVEL,
        )
        script_cache = ScriptCache(
            cache_dir=self._script_cache_dir(),
            http_client=httpx.Client(
                timeout=10.0, trust_env=False, follow_redirects=False
            ),
            enabled=self._runtime_config.registry.scripts_enabled,
        )
        sandbox = ScriptSandbox(enabled=self._runtime_config.registry.scripts_enabled)

        for repo in self._runtime_config.source_repos.enabled_repos:
            manifest = self._manifest_cache.get_manifest(repo)
            if manifest is None:
                continue
            repo_id = manifest.get("repo_id", "")
            for source in manifest.get("sources", []):
                source_type = source.get("type")
                if source_type == "ott-instance":
                    self._build_instance_client(clients, source)
                elif source_type == "ott-rule":
                    self._build_rule_client(clients, source, interpreter, repo_id)
                elif source_type == "ott-script":
                    self._build_script_client(clients, source, script_cache, sandbox)
        return clients

    def _script_cache_dir(self) -> Path:
        from ..config.app_paths import registry_cache_dir

        return registry_cache_dir() / "scripts"

    def _build_instance_client(
        self,
        clients: dict[str, _InstanceClient | _RuleClient],
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
            config=self._runtime_config.registry,
            cache_dir=cache_dir,
            http_client=httpx.Client(
                timeout=10.0, trust_env=False, follow_redirects=False
            ),
            async_executor=None,
        )
        clients[authority] = _InstanceClient(
            authority=authority,
            endpoints=endpoints,
            cache=cache,
            max_content_bytes=self._max_content_bytes,
        )

    @staticmethod
    def _build_rule_client(
        clients: dict[str, _InstanceClient | _RuleClient],
        source: dict,
        interpreter: OttRuleInterpreter,
        repo_id: str = "",
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
        )

    @staticmethod
    def _build_script_client(
        clients: dict[str, _InstanceClient | _RuleClient | _ScriptClient],
        source: dict,
        script_cache: ScriptCache,
        sandbox: ScriptSandbox,
    ) -> None:
        url = source.get("url", "")
        if not url:
            return
        label = source.get("label", "")
        # 用 URL 的 hash 作为 authority key（避免重复下载同脚本）
        key = f"script:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"
        if key in clients:
            return
        clients[key] = _ScriptClient(
            url=url,
            label=label,
            script_cache=script_cache,
            sandbox=sandbox,
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
        for e in all_entries:
            key = f"{e.get('_authority', '')}:{e.get('entry_id', '')}"
            if key in seen:
                continue
            seen[key] = e
        return list(seen.values())

    def list_all_sources(self) -> list[dict]:
        clients = self._build_clients()
        if not clients:
            return []
        all_sources: list[dict] = []
        seen: dict[str, dict] = {}
        for authority, client in clients.items():
            sources = client.list_sources()
            if sources:
                for s in sources:
                    if isinstance(s, dict):
                        s["_authority"] = authority
                    key = (
                        f"{authority}:{s.get('source_key', '')}"
                        if isinstance(s, dict)
                        else ""
                    )
                    if key and key not in seen:
                        seen[key] = s
                        all_sources.append(s)
        return all_sources

    def get_entry(self, authority: str, entry_id: str) -> dict | None:
        clients = self._build_clients()
        client = clients.get(authority)
        if client is None:
            return None
        return client.get_entry(entry_id)

    def get_segment(
        self,
        authority: str,
        entry_id: str,
        revision_id: str,
        segment_index: int,
        segment_size: int = 1000,
    ) -> dict | None:
        clients = self._build_clients()
        client = clients.get(authority)
        if client is None:
            return None
        return client.get_segment(entry_id, revision_id, segment_index, segment_size)

    def list_repos(self) -> list[dict]:
        """返回已启用订阅及其 manifest 摘要（供 UI 订阅管理使用）。"""
        result: list[dict] = []
        for repo in self._runtime_config.source_repos.repos:
            if not repo.url:
                continue
            manifest = self._manifest_cache.get_manifest(repo)
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
                        authorities.append("script")
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
            }
            result.append(summary)
        return result
