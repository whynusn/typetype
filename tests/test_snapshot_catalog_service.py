"""SnapshotCatalogService：物化写快照、快照优先载入（零 fetch）、刷新换新。"""

from __future__ import annotations

from src.backend.application.services.snapshot_catalog_service import (
    SnapshotCatalogService,
)
from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_ON_DEMAND,
    RefreshPolicy,
)


class _FakeFederation:
    def __init__(self, entries):
        self._entries = entries
        self.get_entry_calls = []
        self.last_fetch = None
        self.list_all_calls = 0

    def list_all_entries(self, force=False):
        self.list_all_calls += 1
        return list(self._entries)

    def refresh_source(self, authority, force=True):
        return [e for e in self._entries if e.get("_authority") == authority]

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


def test_load_entry_falls_back_when_snapshot_lacks_content(tmp_path) -> None:
    """instance 源列表物化是摘要（无 content），快照命中但无正文必须兜底拉全文。

    回归：内置 static 源（typetype-builtin-static）载入跟打一直失败——快照
    只有 preview，load_entry 快照优先返回后正文为空，bridge 报「条目无内容」。
    """
    svc, federation = _svc(
        tmp_path,
        [
            {
                "_authority": "auth",
                "entry_id": "e1",
                "preview": "摘要预览",
                "_source_type": "ott-instance",
            }
        ],
    )
    svc.refresh_and_list_all()
    # 快照已落盘但无 content：载入必须兜底 federation.get_entry（带正文）
    federation.last_fetch = {"entry_id": "e1", "content": "全文正文"}
    loaded = svc.load_entry("auth", "e1")
    assert loaded is not None and loaded["content"] == "全文正文"
    assert federation.get_entry_calls == [("auth", "e1")]


def test_refresh_source_materializes_new_snapshot(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [])
    # 首次：无条目
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is None
    # 第二次：federation 有内容 → 换新
    federation._entries = [_entry()]
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is not None


def test_refresh_source_only_materializes_own_authority(tmp_path) -> None:
    """refresh_source 只物化目标 authority，不再全量列所有源（旧实现回归）。"""
    svc, federation = _svc(tmp_path, [])
    federation._entries = [
        _entry(authority="auth-a", entry_id="a1"),
        _entry(authority="auth-b", entry_id="b1"),
    ]
    svc.refresh_source("auth-a")
    # 单源刷新走 federation.refresh_source，不触碰全量 list_all_entries
    assert federation.list_all_calls == 0
    assert svc.load_entry("auth-a", "a1") is not None
    assert svc.load_entry("auth-b", "b1") is None


def test_refresh_and_list_all_forces_passthrough(tmp_path) -> None:
    """总刷新 force 必须透传到 federation（绕过条目缓存重新物化）。"""
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all(force=True)
    assert federation.list_all_calls == 1


def test_prune_applies_on_refresh(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [], max_per_source=2)
    for i in range(5):
        federation._entries = [_entry(entry_id=f"e{i}", content=f"c{i}")]
        svc.refresh_source("auth")
    assert svc.load_entry("auth", "e4") is not None
    assert svc.load_entry("auth", "e0") is None
    assert svc.load_entry("auth", "e1") is None


def test_refresh_and_list_keeps_all_live_entries(tmp_path) -> None:
    """本源 >5 条活跃条目必须全部列出（回归：旧 prune 截断最旧 N 条）。"""
    svc, federation = _svc(tmp_path, [], max_per_source=5)
    federation._entries = [_entry(entry_id=f"e{i}", content=f"c{i}") for i in range(6)]
    result = svc.refresh_and_list_all()
    assert len(result) == 6
    assert sorted(e["entry_id"] for e in result) == [f"e{i}" for i in range(6)]
    for i in range(6):
        assert svc.load_entry("auth", f"e{i}") is not None


def test_prune_stale_removes_no_longer_live_snapshots(tmp_path) -> None:
    """不再活跃的旧快照仍会被 prune（live 集之外，超限部分删除）。"""
    svc, federation = _svc(tmp_path, [], max_per_source=5)
    for i in range(8):
        federation._entries = [_entry(entry_id=f"e{i}", content=f"c{i}")]
        svc.refresh_source("auth")
    # 当前 live 只有 e7；旧快照 e0-e6 均为 stale，超限（保留最近 5 条）的被删除
    assert svc.load_entry("auth", "e7") is not None
    assert svc.load_entry("auth", "e6") is not None
    assert svc.load_entry("auth", "e5") is not None
    assert svc.load_entry("auth", "e4") is not None
    assert svc.load_entry("auth", "e3") is not None
    assert svc.load_entry("auth", "e2") is not None
    assert svc.load_entry("auth", "e1") is None
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


def test_list_cached_returns_snapshots_without_network(tmp_path) -> None:
    """进入开源文库首屏：只读已落盘快照（零网络），不触发物化。"""
    svc, federation = _svc(tmp_path, [_entry()])
    # 首次物化落盘
    svc.refresh_and_list_all()
    calls_before = federation.list_all_calls
    # 再进 tab：只读快照，不再调 federation
    result = svc.list_cached()
    assert len(result) == 1
    assert result[0]["entry_id"] == "e1"
    assert federation.list_all_calls == calls_before  # 零网络


def test_refresh_returns_full_store_when_source_fails(tmp_path) -> None:
    """部分源物化失败时，refresh_and_list_all 仍返回全部已存快照（视图不收缩）。

    回归：返回值曾只含本次物化成功的源——网络失败/超时的源整个从视图消失
    （「点击刷新后变少了很多」），其快照明明仍在存储里。
    """
    svc, federation = _svc(tmp_path, [])
    # 首次：两个源都成功 → 全部落盘
    federation._entries = [
        _entry(authority="auth-a", entry_id="a1"),
        _entry(authority="auth-b", entry_id="b1"),
    ]
    first = svc.refresh_and_list_all()
    assert {e["entry_id"] for e in first} == {"a1", "b1"}

    # 第二次：auth-b 网络失败（federation 只返回 auth-a）
    federation._entries = [_entry(authority="auth-a", entry_id="a1")]
    second = svc.refresh_and_list_all()
    # 视图 = 当前全部已存快照：b1 快照仍在（不收缩，可继续载入）
    assert {e["entry_id"] for e in second} == {"a1", "b1"}
    b_snap = next(e for e in second if e["entry_id"] == "b1")
    # rule 源为 on_demand 策略（freshness 恒 "on_demand" 随机徽章）；快照仍在即回归成立
    assert b_snap["freshness"] == "on_demand"
    assert svc.load_entry("auth-b", "b1") is not None  # 旧快照仍可载入


def test_list_all_returns_snapshots_across_authorities(tmp_path) -> None:
    """store.list_all 遍历所有 authority 返回全部快照（含 freshness 元数据）。"""
    store = EntrySnapshotStore(tmp_path)
    store.save(
        _entry(authority="auth-a", entry_id="a1"),
        captured_at=100.0,
        policy=RefreshPolicy(MODE_INTERVAL, 10),
    )
    store.save(
        _entry(authority="auth-b", entry_id="b1"),
        captured_at=50.0,
        policy=RefreshPolicy(MODE_INTERVAL, 10),
    )
    all_snaps = store.list_all()
    assert len(all_snaps) == 2
    # 按 captured_at 倒序
    assert all_snaps[0]["entry_id"] == "a1"
    assert all_snaps[1]["entry_id"] == "b1"
    # 每个快照带 _authority 与 freshness 元数据（decorate 前原始快照含 policy）
    assert all_snaps[0]["_authority"] == "auth-a"


# ----------------------------------------------------------------------
# captured_at 语义：后台 revalidate（非 force）不得虚刷 freshness
# ----------------------------------------------------------------------


def test_revalidate_keeps_captured_at_when_content_unchanged(
    tmp_path, monkeypatch
) -> None:
    """后台 revalidate（非 force）内容未变时保留原 captured_at（freshness 不虚刷）。

    回归：refresh_and_list_all 曾对所有返回条目无条件 save(captured_at=now)
    ——缓存命中的源即使没重新抓取，freshness 徽章/相对时间也被虚刷成
    「最新/刚刚」；现在指纹相同 → 跳过 save。
    """
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all()
    assert svc._store.get("auth", "e1")["captured_at"] == 1000.0

    # 同内容非 force revalidate（模拟再次进入 tab 的后台刷新）
    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    result = svc.refresh_and_list_all()
    assert svc._store.get("auth", "e1")["captured_at"] == 1000.0  # 不被虚刷
    assert result[0]["captured_at"] == 1000.0  # 视图 freshness 同样基于原时间戳


def test_revalidate_updates_captured_at_when_content_changed(
    tmp_path, monkeypatch
) -> None:
    """内容真正变化（TTL 过期源重抓返回新内容）时 captured_at 正常更新。"""
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry(content="hello")])
    svc.refresh_and_list_all()

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    federation._entries = [_entry(content="world")]  # 内容变化
    svc.refresh_and_list_all()
    snap = svc._store.get("auth", "e1")
    assert snap["content"] == "world"
    assert snap["captured_at"] == 2000.0  # 内容变 → 更新


def test_force_refresh_always_updates_captured_at(tmp_path, monkeypatch) -> None:
    """手动总刷新（force）无条件更新 captured_at——即使内容相同（确实重新抓了）。"""
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all()
    assert svc._store.get("auth", "e1")["captured_at"] == 1000.0

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    svc.refresh_and_list_all(force=True)  # 同内容 force → 无条件更新
    assert svc._store.get("auth", "e1")["captured_at"] == 2000.0

    monkeypatch.setattr(scs.time, "time", lambda: 3000.0)
    svc.refresh_and_list_all()  # 非 force 同内容 → 保留
    assert svc._store.get("auth", "e1")["captured_at"] == 2000.0


def test_revalidate_legacy_snapshot_without_fingerprint_updates_once(
    tmp_path,
) -> None:
    """旧版本快照无 snap_fingerprint：首次 revalidate 补写指纹（更新一次），
    之后内容未变不再更新。"""
    store = EntrySnapshotStore(tmp_path)
    store.save(
        _entry(), captured_at=111.0, policy=RefreshPolicy(MODE_ON_DEMAND)
    )
    svc = SnapshotCatalogService(_FakeFederation([_entry()]), store, None)

    # 非 force revalidate：旧快照无指纹 → 视为已变，补写指纹 + 更新 captured_at
    svc.refresh_and_list_all()
    snap = store.get("auth", "e1")
    assert snap is not None
    assert snap["captured_at"] != 111.0
    assert snap.get("snap_fingerprint")

    # 之后内容未变 → 不再更新
    svc.refresh_and_list_all()
    assert store.get("auth", "e1")["captured_at"] == snap["captured_at"]


# ----------------------------------------------------------------------
# 订阅源（repo）级刷新 / 删除清理（条目按 _repo_id 动态归组）
# ----------------------------------------------------------------------


class _RepoFakeFederation(_FakeFederation):
    """带 authority↔repo 归属映射的 fake（模拟 federation 注入 + 反查）。"""

    def __init__(self, entries, repo_map=None):
        super().__init__(entries)
        self._repo_map = repo_map or {}

    def authorities_of_repo(self, repo_id):
        return list(self._repo_map.get(repo_id, []))


def test_refresh_repo_only_materializes_its_authorities(tmp_path) -> None:
    """repo 级刷新只物化该 repo 下的 authority（其他 repo 零调用、快照不动）。"""
    fed = _RepoFakeFederation(
        [
            _entry(authority="auth-a", entry_id="a1"),
            _entry(authority="auth-b", entry_id="b1"),
        ],
        repo_map={"repo-1": ["auth-a"], "repo-2": ["auth-b"]},
    )
    svc = SnapshotCatalogService(fed, EntrySnapshotStore(tmp_path), None)

    result = svc.refresh_repo("repo-1")

    assert svc.load_entry("auth-a", "a1") is not None   # 该 repo 已物化
    assert svc.load_entry("auth-b", "b1") is None       # 其他 repo 零调用
    assert {e["entry_id"] for e in result} == {"a1"}    # 视图 = 存储


def test_remove_repo_clears_snapshots_of_its_authorities(tmp_path) -> None:
    """删除订阅：清理该 repo 下全部 authority 的快照残留。"""
    fed = _RepoFakeFederation(
        [_entry(authority="auth-a", entry_id="a1")],
        repo_map={"repo-1": ["auth-a"]},
    )
    store = EntrySnapshotStore(tmp_path)
    svc = SnapshotCatalogService(fed, store, None)
    svc.refresh_and_list_all()
    assert svc.load_entry("auth-a", "a1") is not None

    svc.remove_repo("repo-1")

    assert svc.load_entry("auth-a", "a1") is None
