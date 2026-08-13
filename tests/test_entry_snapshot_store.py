"""EntrySnapshotStore：快照落盘/读取/prune/调度到期。"""

from __future__ import annotations

from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_STATIC,
    RefreshPolicy,
)


def _entry(authority: str, entry_id: str, content: str = "text") -> dict:
    return {"_authority": authority, "entry_id": entry_id, "content": content}


def test_save_get_roundtrip(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "e1"), captured_at=1000.0, policy=RefreshPolicy(MODE_STATIC))
    got = s.get("auth", "e1")
    assert got is not None
    assert got["entry_id"] == "e1"
    assert got["_authority"] == "auth"
    assert got["captured_at"] == 1000.0


def test_missing_returns_none(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    assert s.get("auth", "nope") is None


def test_list_orders_by_captured_at_desc(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "old"), captured_at=100.0, policy=RefreshPolicy(MODE_STATIC))
    s.save(_entry("auth", "new"), captured_at=200.0, policy=RefreshPolicy(MODE_STATIC))
    ids = [e["entry_id"] for e in s.list("auth")]
    assert ids == ["new", "old"]


def test_prune_keeps_latest_n(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path, max_per_source=2)
    for i in range(4):
        s.save(
            _entry("auth", f"e{i}"),
            captured_at=float(i),
            policy=RefreshPolicy(MODE_STATIC),
        )
    s.prune("auth")
    ids = [e["entry_id"] for e in s.list("auth")]
    assert ids == ["e3", "e2"]


def test_prune_stale_never_deletes_live_ids(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path, max_per_source=2)
    for i in range(6):
        s.save(
            _entry("auth", f"e{i}"),
            captured_at=float(i),
            policy=RefreshPolicy(MODE_STATIC),
        )
    # live 集含全部 6 条：即使超 max_per_source 也一律不删
    s.prune_stale("auth", {f"e{i}" for i in range(6)})
    assert len(s.list("auth")) == 6
    # live 集之外且超限的旧快照被清理（保留最近 2 条 stale：e5/e4）
    s.prune_stale("auth", {"e6"})
    ids = [e["entry_id"] for e in s.list("auth")]
    assert ids == ["e5", "e4"]


def test_due_for_refresh_only_interval(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(
        _entry("auth", "iv"), captured_at=0.0, policy=RefreshPolicy(MODE_INTERVAL, 10)
    )
    s.save(_entry("auth", "od"), captured_at=0.0, policy=RefreshPolicy("on_demand"))
    due = s.due_for_refresh(now=15.0)
    assert ("auth", "iv") in due
    assert ("auth", "od") not in due


def test_corrupt_file_returns_none(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "e1"), captured_at=0.0, policy=RefreshPolicy(MODE_STATIC))
    from src.backend.integration.entry_snapshot_store import _authority_hash

    p = tmp_path / "snapshots" / _authority_hash("auth") / "e1.json"
    p.write_text("{broken", encoding="utf-8")
    assert s.get("auth", "e1") is None
