"""动态源快照目录编排层。

- 联邦物化 → 逐条写快照 → prune → 返回带 freshness 的摘要列表
- load_entry：快照命中直接返回（不重新执行规则/脚本），miss 兜底 federation
- 调度：scheduled_tick 只刷新 interval 模式到期源（on_demand 仅手动）
- 用户 per-source 覆盖（config.source_refresh_overrides）> 推断
- captured_at 语义（2026-08-14 修正）：表示「最近一次内容落盘」——后台
  revalidate（非 force）对内容未变的快照跳过 save（指纹相同），不虚刷
  freshness；手动刷新（force / refresh_source）无条件更新
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

from ...integration.entry_snapshot_store import EntrySnapshotStore
from ...integration.refresh_policy import (
    MODE_INTERVAL,
    RefreshPolicy,
    infer_policy,
    source_type_of,
)
from ...integration.source_status_store import SourceStatusStore

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig
    from ...integration.ott_federation_provider import OttFederationProvider
    from ...ports.async_executor import AsyncExecutor


def _content_fingerprint(entry: dict) -> str:
    """物化条目的内容指纹（展示相关内容字段的规范化哈希）。

    instance 摘要（normalize_summary）与 rule/script/bridge 条目没有统一
    content_hash 字段，故按列表展示/载入相关的字段自算；与 captured_at、
    freshness 等装饰/元数据字段无关（那些不进指纹）。
    """
    parts = {
        "title": entry.get("title", ""),
        "preview": entry.get("preview", ""),
        "content": entry.get("content", ""),
        "char_count": entry.get("char_count", entry.get("charCount", "")),
        "content_mode": entry.get("content_mode", ""),
        "current_revision_id": entry.get("current_revision_id", ""),
        "segment_count": entry.get("segment_count", ""),
        "segment_size_hint": entry.get("segment_size_hint", ""),
        "source_label": entry.get("source_label", ""),
        "category": entry.get("category", ""),
        "tags": sorted(entry.get("tags", []) or [], key=str),
    }
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SnapshotCatalogService:
    def __init__(
        self,
        federation: "OttFederationProvider",
        store: EntrySnapshotStore,
        runtime_config: "RuntimeConfig | None",
        async_executor: "AsyncExecutor | None" = None,
        max_per_source: int = 5,
        status_store: "SourceStatusStore | None" = None,
    ) -> None:
        self._federation = federation
        self._store = store
        self._runtime_config = runtime_config
        self._async_executor = async_executor
        self._max_per_source = max_per_source
        self._status_store = status_store
        # 最近一次物化的成功/失败 authority（federation 统计透传；供上层
        # 区分「刷新真的成功」与「失败回退缓存快照」）
        self._last_refresh_ok: list[str] = []
        self._last_refresh_failed: list[str] = []

    @property
    def last_refresh_ok(self) -> list[str]:
        return list(self._last_refresh_ok)

    @property
    def last_refresh_failed(self) -> list[str]:
        return list(self._last_refresh_failed)

    def _sync_refresh_stats(self) -> None:
        """透传 federation 最近一次物化的成功/失败 authority 统计。"""
        self._last_refresh_ok = list(getattr(self._federation, "_last_list_ok", ()))
        self._last_refresh_failed = list(
            getattr(self._federation, "_last_list_failed", ())
        )

    # ------------------------------------------------------------------
    # 策略解析（用户覆盖 > 推断）
    # ------------------------------------------------------------------

    def _policy_for(self, entry: dict) -> RefreshPolicy:
        authority = entry.get("_authority", "")
        if self._runtime_config is not None:
            override = self._runtime_config.get_source_refresh_override(authority)
            if isinstance(override, dict):
                return RefreshPolicy.from_dict(override)
        declared = entry.get("_refresh_policy")
        if isinstance(declared, dict) and declared.get("mode"):
            return RefreshPolicy.from_dict(declared)
        return infer_policy(source_type_of(entry))

    # ------------------------------------------------------------------
    # 列表 / 载入
    # ------------------------------------------------------------------

    def list_cached(self) -> list[dict]:
        """只读已落盘快照列表（零网络），供进入开源文库渲染。

        不触发任何物化/刷新；进入 tab 先展示已存快照，后台由
        RefreshScheduler / 手动刷新换新，避免每次进入都白屏等网络。
        """
        now = time.time()
        return [self._decorate(snap, now) for snap in self._store.list_all()]

    def list_source_statuses(self) -> dict[str, dict]:
        """返回 per-authority 健康状态（零网络；未配置 store 时为空）。"""
        if self._status_store is None:
            return {}
        return self._status_store.list_all()

    def _record_source_ok(
        self, authority: str, entries: list[dict], now: float
    ) -> None:
        if self._status_store is None:
            return
        first = next((e for e in entries if isinstance(e, dict)), {})
        policy_entry = dict(first)
        policy_entry["_authority"] = authority
        policy = self._policy_for(policy_entry)
        self._status_store.update(
            authority,
            state="ok",
            checked_at=now,
            source_label=str(first.get("_source_label", first.get("source_label", ""))),
            source_type=str(first.get("_source_type", "")),
            repo_id=str(first.get("_repo_id", "")),
            repo_name=str(first.get("_repo_name", "")),
            repo_url=str(first.get("_repo_url", "")),
            refresh_policy=policy.to_dict(),
        )

    def _record_source_failed(self, authority: str, now: float) -> None:
        if self._status_store is None:
            return
        self._status_store.update(
            authority,
            state="failed",
            message="网络不可达或源不可用",
            checked_at=now,
        )

    def refresh_and_list_all(self, force: bool = False) -> list[dict]:
        """物化 → 逐条写快照 → prune → 返回**当前全部已存快照**（视图 = 存储）。

        物化只负责更新存储（保存新快照 / prune 超限）；返回视图永远等于
        当前已落盘快照集合——**部分源本次物化失败（网络超时等）不使视图
        收缩**：失败源保留旧快照并标记 stale（可刷新），仍可载入。
        视图只随存储变化（过期/prune/手动 force 换新），不随单次物化成败波动。

        force=True（手动总刷新）：绕过各源条目/文件缓存，全部重新物化；
        **内容/归属未变的快照保留原 captured_at，仅写 last_checked_at=now**
        （不再把「刚检查」伪装成「刚更新」）。
        force=False（后台 revalidate）：仅 TTL 过期源重抓，内容未变的
        快照跳过 save 保留原 captured_at——缓存命中条目不虚刷 freshness
        徽章/相对时间（回归：曾对所有返回条目无条件 save(captured_at=now)）。
        """
        entries = self._federation.list_all_entries(force=force) or []
        now = time.time()
        live_ids: dict[str, set[str]] = {}
        entries_by_authority: dict[str, list[dict]] = {}
        for e in entries:
            if not isinstance(e, dict):
                continue
            e.setdefault("_authority", e.get("authority", ""))
            authority = e.get("_authority", "")
            if authority:
                live_ids.setdefault(authority, set()).add(e.get("entry_id"))
                entries_by_authority.setdefault(authority, []).append(e)
            policy = self._policy_for(e)
            fingerprint = _content_fingerprint(e)
            existing = self._store.get(authority, str(e.get("entry_id", "")))
            if not force and self._snapshot_unchanged(e, authority, existing):
                # 后台 revalidate：内容与归属均未变 → 保留原 captured_at
                # （freshness 不被虚刷）
                continue
            captured_at = self._next_captured_at(
                e, authority, existing, fingerprint, now
            )
            self._store.save(
                e,
                captured_at=captured_at,
                policy=policy,
                fingerprint=fingerprint,
                # force 是用户显式「检查」，检查成功时间可推进；
                # 后台路径无法区分缓存命中，保留旧检查时间。
                last_checked_at=now if force else None,
            )
        for authority, ids in live_ids.items():
            self._store.prune_stale(authority, ids, self._max_per_source)
        self._sync_refresh_stats()
        for authority in self._last_refresh_ok:
            self._record_source_ok(
                authority, entries_by_authority.get(authority, []), now
            )
        for authority in self._last_refresh_failed:
            self._record_source_failed(authority, now)
        return self.list_cached()

    def _next_captured_at(
        self,
        entry: dict,
        authority: str,
        existing: dict | None,
        fingerprint: str,
        now: float,
    ) -> float:
        """计算本次物化的 captured_at：内容真正变化才推进时间。

        内容与归属元数据都未变 → 保留旧 captured_at；仅归属元数据变化
        （旧快照补 _repo_*/_source_* 字段）→ 同样保留；内容指纹变化或
        全新条目 → now。
        """
        if existing is None:
            return now
        if self._snapshot_unchanged(entry, authority, existing):
            return float(existing.get("captured_at", now))
        if existing.get("snap_fingerprint") == fingerprint:
            # 内容未变、仅归属元数据缺失/变化：本次只是补写字段
            return float(existing.get("captured_at", now))
        return now

    def _snapshot_unchanged(
        self, entry: dict, authority: str, existing: dict | None = None
    ) -> bool:
        """非 force 物化时的「内容未变」判定（快照指纹 + 归属元数据比对）。

        现有快照缺指纹（旧版本落盘）→ 视为已变（本次 save 补写指纹，一次性）；
        指纹相同 → 内容未变。但归属元数据（_repo_id/_repo_name/_repo_url/
        _repo_max_entries，federation 按 manifest 注入）缺失或变化时仍视为已变
        （2026-08-15：旧构建物化的快照缺 _repo_id，若只比指纹会被永远跳过，
        前端只能按 authority 回退分组，同一订阅源的条目被拆成多个假源组；
        manifest 调整 max_entries 后同样需要补写，否则卡片上限展示不更新）。
        """
        if existing is None:
            existing = self._store.get(authority, str(entry.get("entry_id", "")))
        if existing is None:
            return False
        old = existing.get("snap_fingerprint")
        if not old or old != _content_fingerprint(entry):
            return False
        for field in (
            "_repo_id",
            "_repo_name",
            "_repo_url",
            "_repo_max_entries",
            "_repo_trust_state",
            "_source_label",
            "_source_type",
            "_refresh_policy",
        ):
            if (existing.get(field) or "") != (entry.get(field) or ""):
                return False
        return True

    def load_entry(self, authority: str, entry_id: str) -> dict | None:
        """快照命中且含正文直接返回（不重抽）；否则 federation.get_entry 兜底。

        instance 源的列表物化是摘要（normalize_summary，无 content 字段），
        快照只有预览；选中载入必须拉全文（静态端点按条目文件缓存，重复点击
        不重复打网络）。rule/script/bridge 快照含 content，快照命中零重抽。
        """
        snap = self._store.get(authority, entry_id)
        if snap is not None and snap.get("content"):
            return snap
        return self._federation.get_entry(authority, entry_id)

    def refresh_source(self, authority: str, now: float | None = None) -> None:
        """单源强制刷新（random 换新）：只重新物化该 authority 并落盘。

        经 federation.refresh_source 单源换新（绕过该源条目/文件缓存），
        不再先全量列所有源再过滤（旧实现会无谓重物化其他源）。
        单源刷新是 force 语义（确实重新检查了）：**内容/归属未变 → 保留
        原 captured_at，仅写 last_checked_at=now**；内容变化才推进
        captured_at。修复「静态源点刷新，内容没变却显示刚刚」。
        """
        now = now if now is not None else time.time()
        entries = self._federation.refresh_source(authority) or []
        live_ids: set[str] = set()
        for e in entries:
            if not isinstance(e, dict):
                continue
            entry_id = str(e.get("entry_id", ""))
            if entry_id:
                live_ids.add(e.get("entry_id"))
            policy = self._policy_for(e)
            fingerprint = _content_fingerprint(e)
            existing = self._store.get(authority, entry_id)
            captured_at = self._next_captured_at(
                e, authority, existing, fingerprint, now
            )
            self._store.save(
                e,
                captured_at=captured_at,
                policy=policy,
                fingerprint=fingerprint,
                last_checked_at=now,
            )
        self._store.prune_stale(authority, live_ids, self._max_per_source)
        self._sync_refresh_stats()
        if authority in self._last_refresh_ok:
            self._record_source_ok(authority, entries, now)
        if authority in self._last_refresh_failed:
            self._record_source_failed(authority, now)

    def refresh_repo(self, repo_id: str, now: float | None = None) -> list[dict]:
        """订阅源（repo）级强制刷新：只重新物化该 repo 下的全部 authority。

        组头刷新按订阅源粒度；其他 repo 零调用。
        返回当前全部已存快照（视图 = 存储）。
        """
        now = now if now is not None else time.time()
        ok: list[str] = []
        failed: list[str] = []
        for authority in self._federation.authorities_of_repo(repo_id):
            self.refresh_source(authority, now=now)
            ok += self._last_refresh_ok
            failed += self._last_refresh_failed
        self._last_refresh_ok, self._last_refresh_failed = ok, failed
        return self.list_cached()

    def remove_repo(self, repo_id: str) -> None:
        """删除订阅时清理该 repo 下全部 authority 的快照残留。"""
        for authority in self._federation.authorities_of_repo(repo_id):
            self._store.clear_authority(authority)

    # ------------------------------------------------------------------
    # 调度
    # ------------------------------------------------------------------

    def scheduled_tick(self, now: float | None = None) -> None:
        """扫描 interval 到期源，后台刷新（async_executor 不可用时同步）。

        按 authority 去重：同源多条到期快照只刷新一次（refresh_source 是
        全源物化，重复调用会对同一源做 N 次全量刷新）。
        """
        now = now if now is not None else time.time()
        due = self._store.due_for_refresh(now)
        for authority in {a for a, _entry_id in due}:
            if self._async_executor is not None:
                self._async_executor.submit(
                    lambda a=authority: self.refresh_source(a, now=now)
                )
            else:
                self.refresh_source(authority, now=now)

    # ------------------------------------------------------------------
    # freshness 装饰
    # ------------------------------------------------------------------

    @staticmethod
    def _decorate(entry: dict, now: float) -> dict:
        decorated = dict(entry)
        policy = RefreshPolicy.from_dict(entry.get("refresh_policy"))
        captured = entry.get("captured_at")
        checked = entry.get("last_checked_at")
        if isinstance(captured, (int, float)):
            decorated["captured_at"] = captured
            decorated["last_fetched_relative"] = _relative_time(now - captured)
            nra = policy.next_refresh_at(float(captured))
            decorated["next_refresh_at"] = nra
            if policy.mode == MODE_INTERVAL:
                decorated["freshness"] = (
                    "fresh" if (nra is not None and nra > now) else "stale"
                )
            elif policy.mode == "on_demand":
                decorated["freshness"] = "on_demand"
            else:
                decorated["freshness"] = "fresh"
        if isinstance(checked, (int, float)):
            decorated["last_checked_at"] = checked
            decorated["last_checked_relative"] = _relative_time(now - checked)
            # 检查时间明显晚于内容变化时间 → 最近一次刷新「内容无变化」
            decorated["checked_without_change"] = bool(
                isinstance(captured, (int, float)) and checked >= captured + 1.0
            )
        return decorated


def _relative_time(seconds: float) -> str:
    """秒差 → 「刚刚 / N 分钟前 / N 小时前 / N 天前」（UI 展示用，中英双语由 qsTr 在 QML 侧）。"""
    seconds = max(0, seconds)
    if seconds < 60:
        return "刚刚"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} 小时前"
    return f"{int(hours // 24)} 天前"
