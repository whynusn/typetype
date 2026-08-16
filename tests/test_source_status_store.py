"""SourceStatusStore：per-authority 健康状态持久化与容错。"""

from __future__ import annotations

import json

from src.backend.integration.source_status_store import SourceStatusStore


def test_status_defaults_when_missing(tmp_path) -> None:
    store = SourceStatusStore(tmp_path)
    status = store.get("rule:repo:r1")
    assert status["state"] == "unknown"
    assert status["consecutive_failures"] == 0
    assert status["authority"] == "rule:repo:r1"


def test_success_resets_failures_and_persists_metadata(tmp_path) -> None:
    store = SourceStatusStore(tmp_path)
    store.update("rule:repo:r1", state="failed", message="网络不可达", checked_at=10.0)
    store.update("rule:repo:r1", state="failed", message="网络不可达", checked_at=20.0)
    assert store.get("rule:repo:r1")["consecutive_failures"] == 2

    store.update(
        "rule:repo:r1",
        state="ok",
        checked_at=30.0,
        source_label="一言",
        source_type="ott-rule",
        repo_name="OTT Source Hub",
    )
    status = store.get("rule:repo:r1")
    assert status["state"] == "ok"
    assert status["consecutive_failures"] == 0
    assert status["source_label"] == "一言"
    assert status["last_success_at"] == 30.0


def test_failure_metadata_is_preserved(tmp_path) -> None:
    """失败刷新不应丢掉之前记录的展示名（组头还要用）。"""
    store = SourceStatusStore(tmp_path)
    store.update(
        "a1", state="ok", source_label="经典中文短句", source_type="ott-instance"
    )
    store.update("a1", state="failed", message="boom", checked_at=5.0)
    status = store.get("a1")
    assert status["state"] == "failed"
    assert status["source_label"] == "经典中文短句"
    assert status["source_type"] == "ott-instance"


def test_corrupt_file_returns_default(tmp_path) -> None:
    store = SourceStatusStore(tmp_path)
    store.update("a1", state="ok")
    path = store._path("a1")
    path.write_text("{not json", encoding="utf-8")
    assert store.get("a1")["state"] == "unknown"


def test_list_all_returns_persisted_statuses(tmp_path) -> None:
    store = SourceStatusStore(tmp_path)
    store.update("a1", state="ok")
    store.update("a2", state="failed", message="x")
    all_statuses = store.list_all()
    assert set(all_statuses) == {"a1", "a2"}
    assert all_statuses["a2"]["state"] == "failed"
    assert isinstance(json.dumps(all_statuses), str)
