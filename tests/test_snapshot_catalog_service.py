"""SnapshotCatalogService：物化写快照、快照优先载入（零 fetch）、刷新换新。"""

from __future__ import annotations

from src.backend.application.services.snapshot_catalog_service import (
    SnapshotCatalogService,
)
from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    RefreshPolicy,
)


class _FakeFederation:
    def __init__(self, entries):
        self._entries = entries
        self.get_entry_calls = []
        self.last_fetch = None

    def list_all_entries(self):
        return list(self._entries)

    def get_entry(self, authority, entry_id):
        self.get_entry_calls.append((authority, entry_id))
        return self.last_fetch


def _svc(tmp_path, entries, runtime_config=None, max_per_source=5):
    federation = _FakeFederation(entries)
    store = EntrySnapshotStore(tmp_path)
    return SnapshotCatalogService(
        federation, store, runtime_config, max_per_source=max_per_source
    ), federation


def _entry(authority="auth", entry_id="e1", content="hello", source_type="ott-rule"):
    return {
        "_authority": authority,
        "entry_id": entry_id,
        "content": content,
        "_source_type": source_type,
    }


def test_refresh_and_list_persists_snapshot(tmp_path) -> None:
    svc, _ = _svc(tmp_path, [_entry()])
    result = svc.refresh_and_list_all()
    assert len(result) == 1
    # 物化结果已落盘：载入从快照取，不重抽
    loaded = svc.load_entry("auth", "e1")
    assert loaded is not None and loaded["content"] == "hello"


def test_load_entry_does_not_refetch_when_snapshot_hits(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all()
    svc.load_entry("auth", "e1")
    assert federation.get_entry_calls == []  # 零 fetch —— 失配修复回归


def test_load_entry_falls_back_to_federation_on_miss(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [_entry()])
    federation.last_fetch = {"entry_id": "ghost", "content": "fallback"}
    loaded = svc.load_entry("auth", "ghost")
    assert loaded is not None and loaded["content"] == "fallback"
    assert federation.get_entry_calls == [("auth", "ghost")]


def test_refresh_source_materializes_new_snapshot(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [])
    # 首次：无条目
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is None
    # 第二次：federation 有内容 → 换新
    federation._entries = [_entry()]
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is not None


def test_prune_applies_on_refresh(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [], max_per_source=2)
    for i in range(3):
        federation._entries = [_entry(entry_id=f"e{i}", content=f"c{i}")]
        svc.refresh_source("auth")
    assert svc.load_entry("auth", "e2") is not None
    assert svc.load_entry("auth", "e0") is None


def test_scheduled_tick_refreshes_interval_due(tmp_path) -> None:
    # interval 到期 → 后台/同步刷新；刷新后快照 captured_at 前移
    fed = _FakeFederation([_entry()])
    store = EntrySnapshotStore(tmp_path)
    store.save(_entry(), captured_at=0.0, policy=RefreshPolicy(MODE_INTERVAL, 10))
    svc = SnapshotCatalogService(fed, store, None)
    svc.scheduled_tick(now=15.0)  # 无 async_executor → 同步
    refreshed = store.get("auth", "e1")
    assert refreshed is not None
    assert refreshed["captured_at"] == 15.0
