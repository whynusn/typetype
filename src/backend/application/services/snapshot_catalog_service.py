"""动态源快照目录编排层。

- 联邦物化 → 逐条写快照 → prune → 返回带 freshness 的摘要列表
- load_entry：快照命中直接返回（不重新执行规则/脚本），miss 兜底 federation
- 调度：scheduled_tick 只刷新 interval 模式到期源（on_demand 仅手动）
- 用户 per-source 覆盖（config.source_refresh_overrides）> 推断
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ...integration.entry_snapshot_store import EntrySnapshotStore
from ...integration.refresh_policy import (
    MODE_INTERVAL,
    RefreshPolicy,
    infer_policy,
    source_type_of,
)

if TYPE_CHECKING:
    from ...config.runtime_config import RuntimeConfig
    from ...integration.ott_federation_provider import OttFederationProvider
    from ...ports.async_executor import AsyncExecutor


class SnapshotCatalogService:
    def __init__(
        self,
        federation: "OttFederationProvider",
        store: EntrySnapshotStore,
        runtime_config: "RuntimeConfig | None",
        async_executor: "AsyncExecutor | None" = None,
        max_per_source: int = 5,
    ) -> None:
        self._federation = federation
        self._store = store
        self._runtime_config = runtime_config
        self._async_executor = async_executor
        self._max_per_source = max_per_source

    # ------------------------------------------------------------------
    # 策略解析（用户覆盖 > 推断）
    # ------------------------------------------------------------------

    def _policy_for(self, entry: dict) -> RefreshPolicy:
        authority = entry.get("_authority", "")
        if self._runtime_config is not None:
            override = self._runtime_config.get_source_refresh_override(authority)
            if isinstance(override, dict):
                return RefreshPolicy.from_dict(override)
        return infer_policy(source_type_of(entry))

    # ------------------------------------------------------------------
    # 列表 / 载入
    # ------------------------------------------------------------------

    def refresh_and_list_all(self) -> list[dict]:
        """物化 → 逐条写快照 → prune 过期 → 返回快照（含 freshness 元数据）列表。

        返回**落盘后的快照**（而非原始 federation 条目）——freshness 字段
        （captured_at/refresh_policy/next_refresh_at）只存在于快照内。
        prune 只清理不再活跃（不在当前 live 集）的旧快照，活跃条目永不删除，
        因此本源全部条目都出现在返回目录中（回归修复：旧 prune 会截断最旧 N 条）。
        """
        entries = self._federation.list_all_entries() or []
        now = time.time()
        live_ids: dict[str, set[str]] = {}
        for e in entries:
            if not isinstance(e, dict):
                continue
            e.setdefault("_authority", e.get("authority", ""))
            authority = e.get("_authority", "")
            if authority:
                live_ids.setdefault(authority, set()).add(e.get("entry_id"))
            policy = self._policy_for(e)
            self._store.save(e, captured_at=now, policy=policy)
        for authority, ids in live_ids.items():
            self._store.prune_stale(authority, ids, self._max_per_source)
        result: list[dict] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            snap = self._store.get(e.get("_authority", ""), e.get("entry_id", ""))
            if snap is not None:
                result.append(self._decorate(snap, now))
        return result

    def load_entry(self, authority: str, entry_id: str) -> dict | None:
        """快照命中直接返回（不重抽）；miss → federation.get_entry 兜底。"""
        snap = self._store.get(authority, entry_id)
        if snap is not None:
            return snap
        return self._federation.get_entry(authority, entry_id)

    def refresh_source(self, authority: str, now: float | None = None) -> None:
        """单源强制刷新（random 换新）：重新物化该 authority 全部条目并落盘。"""
        now = now if now is not None else time.time()
        live_ids: set[str] = set()
        for e in self._federation.list_all_entries() or []:
            if not isinstance(e, dict):
                continue
            if e.get("_authority") != authority:
                continue
            live_ids.add(e.get("entry_id"))
            policy = self._policy_for(e)
            self._store.save(e, captured_at=now, policy=policy)
        self._store.prune_stale(authority, live_ids, self._max_per_source)

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
