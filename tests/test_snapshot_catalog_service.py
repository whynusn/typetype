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
    """联邦层契约替身（ADR-016 B1）：list_authorities + materialize。

    ``failing``：这些 authority 的物化返回 None（源不可用）。
    """

    def __init__(self, entries):
        self._entries = entries
        self.get_entry_calls = []
        self.last_fetch = None
        self.materialize_calls: list[str] = []
        self.failing: set[str] = set()

    def list_authorities(self):
        seen: list[str] = []
        for e in self._entries:
            a = e.get("_authority", "")
            if a and a not in seen:
                seen.append(a)
        return seen + [a for a in sorted(self.failing) if a not in seen]

    def materialize(self, authority):
        self.materialize_calls.append(authority)
        if authority in self.failing or authority not in self.list_authorities():
            return None
        return [dict(e) for e in self._entries if e.get("_authority") == authority]

    def authority_repo_urls(self):
        return {
            e.get("_authority", ""): e.get("_repo_url", "")
            for e in self._entries
            if e.get("_authority") and e.get("_authority") not in self.failing
        }

    def authorities_of_repo(self, repo_id):
        return []

    @property
    def list_all_calls(self):
        return len(self.materialize_calls)

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
    # 单源刷新只物化目标 authority
    assert federation.materialize_calls == ["auth-a"]
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
        svc.refresh_source("auth", now=float(i))
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
        svc.refresh_source("auth", now=float(i))
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
    svc.refresh_and_list_all(force=True)

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    federation._entries = [_entry(content="world")]  # 内容变化
    svc.refresh_and_list_all(force=True)
    snap = svc._store.get("auth", "e1")
    assert snap["content"] == "world"
    assert snap["captured_at"] == 2000.0  # 内容变 → 更新


def test_force_refresh_keeps_captured_at_when_content_unchanged(
    tmp_path, monkeypatch
) -> None:
    """手动总刷新（force）内容未变时保留 captured_at，只推进 last_checked_at。

    回归：force 曾无条件 save(captured_at=now)，静态源点「检查更新」后
    内容没变却显示「刚刚」；现在 captured_at 只在内容实际变化时推进。
    """
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all()
    snap = svc._store.get("auth", "e1")
    assert snap["captured_at"] == 1000.0
    assert snap["last_checked_at"] == 1000.0

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    svc.refresh_and_list_all(force=True)  # 同内容 force → 不虚刷内容时间
    snap = svc._store.get("auth", "e1")
    assert snap["captured_at"] == 1000.0
    assert snap["last_checked_at"] == 2000.0  # 检查时间推进

    result = svc.refresh_and_list_all(force=True)
    assert result[0]["captured_at"] == 1000.0
    assert result[0]["last_checked_at"] == 2000.0
    assert result[0]["checked_without_change"] is True


def test_refresh_source_keeps_captured_at_for_unchanged_static(
    tmp_path, monkeypatch
) -> None:
    """源级刷新内容未变：保留 captured_at，仅写 last_checked_at（用户报告修复）。"""
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_source("auth")
    snap = svc._store.get("auth", "e1")
    assert snap["captured_at"] == 1000.0
    assert snap["last_checked_at"] == 1000.0

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    svc.refresh_source("auth")
    snap = svc._store.get("auth", "e1")
    assert snap["captured_at"] == 1000.0  # 内容未变 → 时间不虚刷
    assert snap["last_checked_at"] == 2000.0  # 检查时间推进


def test_refresh_source_updates_captured_at_when_content_changed(
    tmp_path, monkeypatch
) -> None:
    """源级刷新内容真正变化：captured_at 与 last_checked_at 同步推进。"""
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, federation = _svc(tmp_path, [_entry(content="hello")])
    svc.refresh_source("auth")

    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    federation._entries = [_entry(content="world")]
    svc.refresh_source("auth")
    snap = svc._store.get("auth", "e1")
    assert snap["captured_at"] == 2000.0
    assert snap["last_checked_at"] == 2000.0


def test_revalidate_legacy_snapshot_without_fingerprint_updates_once(
    tmp_path,
) -> None:
    """旧版本快照无 snap_fingerprint：首次 revalidate 补写指纹（更新一次），
    之后内容未变不再更新。"""
    store = EntrySnapshotStore(tmp_path)
    store.save(_entry(), captured_at=111.0, policy=RefreshPolicy(MODE_ON_DEMAND))
    svc = SnapshotCatalogService(_FakeFederation([_entry()]), store, None)

    # 非 force revalidate：旧快照无指纹 → 视为已变，补写指纹 + 更新 captured_at
    svc.refresh_and_list_all(force=True)
    snap = store.get("auth", "e1")
    assert snap is not None
    assert snap["captured_at"] != 111.0
    assert snap.get("snap_fingerprint")

    # 之后内容未变 → 不再更新
    svc.refresh_and_list_all(force=True)
    assert store.get("auth", "e1")["captured_at"] == snap["captured_at"]


def test_revalidate_backfills_missing_repo_id_without_touching_captured_at(
    tmp_path, monkeypatch
) -> None:
    """旧构建快照缺 _repo_id：revalidate 必须补写归属字段（分组键自愈），
    但内容未变时保留原 captured_at（freshness 不虚刷）。

    回归：旧快照带 snap_fingerprint 且内容未变时曾被永久跳过 save——
    前端只能按 authority 回退分组，同一订阅源的条目被拆成多个假源组。
    """
    import src.backend.application.services.snapshot_catalog_service as scs

    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    # 旧构建物化：条目无 _repo_id（存量快照）
    legacy = _entry(authority="auth", entry_id="e1", content="hello")
    svc, federation = _svc(tmp_path, [legacy])
    svc.refresh_and_list_all(force=True)
    assert svc._store.get("auth", "e1").get("_repo_id") is None

    # 新构建 revalidate：federation 注入 _repo_id（内容不变）
    monkeypatch.setattr(scs.time, "time", lambda: 2000.0)
    decorated = dict(legacy, _repo_id="repo-1", _repo_name="Repo One")
    federation._entries = [decorated]
    svc.refresh_and_list_all(force=True)

    snap = svc._store.get("auth", "e1")
    assert snap["_repo_id"] == "repo-1"  # 归属字段已补写
    assert snap["captured_at"] == 1000.0  # 内容未变 → freshness 不虚刷

    # 再次 revalidate：内容与归属均一致 → 不再写
    monkeypatch.setattr(scs.time, "time", lambda: 3000.0)
    svc.refresh_and_list_all(force=True)
    assert svc._store.get("auth", "e1")["captured_at"] == 1000.0

    # manifest 调整 max_entries（归属元数据变化）→ 仍需补写（卡片上限展示更新）
    monkeypatch.setattr(scs.time, "time", lambda: 4000.0)
    federation._entries = [dict(decorated, _repo_max_entries=5)]
    svc.refresh_and_list_all(force=True)
    snap = svc._store.get("auth", "e1")
    assert snap["_repo_max_entries"] == 5
    assert snap["captured_at"] == 1000.0  # 仅元数据变化 → 仍不虚刷 freshness


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

    assert svc.load_entry("auth-a", "a1") is not None  # 该 repo 已物化
    assert svc.load_entry("auth-b", "b1") is None  # 其他 repo 零调用
    assert {e["entry_id"] for e in result} == {"a1"}  # 视图 = 存储


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


def test_catalog_tracks_refresh_stats(tmp_path):
    """catalog 自己统计物化成败（last_refresh_ok/failed），不读联邦私有字段，
    供 adapter 区分「刷新成功」与「失败回退缓存快照」。"""
    fed = _FakeFederation([_entry(authority="auth-a")])
    fed.failing = {"auth-b"}
    store = EntrySnapshotStore(tmp_path)
    svc = SnapshotCatalogService(fed, store, None)

    svc.refresh_and_list_all(force=True)
    assert svc.last_refresh_ok == ["auth-a"]
    assert svc.last_refresh_failed == ["auth-b"]

    fed.failing = {"auth-a"}
    svc.refresh_source("auth-a")
    assert svc.last_refresh_ok == []
    assert svc.last_refresh_failed == ["auth-a"]


def test_refresh_source_persists_source_status(tmp_path) -> None:
    """源级刷新成功/失败会写 SourceStatusStore（重启后组头仍有健康状态）。"""
    from src.backend.integration.source_status_store import SourceStatusStore

    fed = _FakeFederation([_entry(source_type="ott-rule")])
    store = EntrySnapshotStore(tmp_path)
    status_store = SourceStatusStore(tmp_path / "status")
    svc = SnapshotCatalogService(fed, store, None, status_store=status_store)

    svc.refresh_source("auth")
    status = status_store.get("auth")
    assert status["state"] == "ok"
    assert status["source_type"] == "ott-rule"
    assert status["last_success_at"] is not None

    fed.failing = {"auth"}
    svc.refresh_source("auth")
    assert status_store.get("auth")["state"] == "failed"
    assert status_store.get("auth")["consecutive_failures"] == 1


def test_list_source_statuses_empty_without_store(tmp_path) -> None:
    svc, _ = _svc(tmp_path, [_entry()])
    assert svc.list_source_statuses() == {}


# ----------------------------------------------------------------------
# ADR-016 B1：后台 revalidate 的门控只在 catalog（_is_due）
# ----------------------------------------------------------------------


def test_revalidate_skips_on_demand_source_with_snapshot(tmp_path) -> None:
    """随机源（on_demand）已有快照：进入文库不换新，只在手动刷新时物化。"""
    svc, fed = _svc(tmp_path, [_entry(source_type="ott-rule")])
    svc.refresh_and_list_all()  # 无快照 → 物化
    assert fed.materialize_calls == ["auth"]
    fed._entries = [_entry(source_type="ott-rule", content="new")]
    svc.refresh_and_list_all()  # 后台 revalidate：on_demand 不动
    assert fed.materialize_calls == ["auth"]
    assert svc.load_entry("auth", "e1")["content"] == "hello"
    svc.refresh_source("auth")  # 手动刷新：换新
    assert svc.load_entry("auth", "e1")["content"] == "new"


def test_revalidate_rechecks_static_source_after_ttl(tmp_path, monkeypatch) -> None:
    """静态源（ott-instance）按 ott.cache_ttl_seconds 后台复查上游变化。"""
    import types

    import src.backend.application.services.snapshot_catalog_service as scs

    config = types.SimpleNamespace(
        ott=types.SimpleNamespace(cache_ttl_seconds=100),
        get_source_refresh_override=lambda authority: None,
    )
    monkeypatch.setattr(scs.time, "time", lambda: 1000.0)
    svc, fed = _svc(
        tmp_path, [_entry(source_type="ott-instance")], runtime_config=config
    )
    svc.refresh_and_list_all()
    assert len(fed.materialize_calls) == 1
    monkeypatch.setattr(scs.time, "time", lambda: 1050.0)
    svc.refresh_and_list_all()  # TTL 内：不复查
    assert len(fed.materialize_calls) == 1
    monkeypatch.setattr(scs.time, "time", lambda: 1101.0)
    svc.refresh_and_list_all()  # TTL 到期：复查
    assert len(fed.materialize_calls) == 2


def test_revalidate_retries_failed_source(tmp_path) -> None:
    """上次失败的源（即使是 on_demand）后台 revalidate 会重试。"""
    from src.backend.integration.source_status_store import SourceStatusStore

    fed = _FakeFederation([_entry(source_type="ott-rule")])
    status_store = SourceStatusStore(tmp_path / "status")
    svc = SnapshotCatalogService(
        fed, EntrySnapshotStore(tmp_path), None, status_store=status_store
    )
    svc.refresh_and_list_all()
    fed.failing = {"auth"}
    svc.refresh_source("auth")
    assert status_store.get("auth")["state"] == "failed"
    fed.failing = set()
    calls = len(fed.materialize_calls)
    svc.refresh_and_list_all()
    assert len(fed.materialize_calls) == calls + 1
    assert status_store.get("auth")["state"] == "ok"


# ----------------------------------------------------------------------
# 订阅生命周期（2026-10-18 review）：视图 = 快照 ∩ 当前订阅状态
# ----------------------------------------------------------------------

REPO_A = "https://a.example/ott-repo.json"
REPO_B = "https://b.example/ott-repo.json"


def _repo_cfg(repos, blocked=None):
    import types

    return types.SimpleNamespace(
        source_repos=types.SimpleNamespace(
            repos=[
                types.SimpleNamespace(url=u, enabled=en, trust_state=ts)
                for u, en, ts in repos
            ]
        ),
        blocked_content_hashes=list(blocked or []),
        ott=types.SimpleNamespace(cache_ttl_seconds=3600),
        get_source_refresh_override=lambda authority: None,
    )


def _owned(authority, repo_url, entry_id="e1", **kw):
    e = _entry(authority=authority, entry_id=entry_id, **kw)
    e["_repo_url"] = repo_url
    e["_repo_id"] = repo_url.split("/")[2]
    return e


def test_disabled_repo_hidden_but_kept_and_restored(tmp_path) -> None:
    cfg = _repo_cfg([(REPO_A, True, "verified"), (REPO_B, True, "verified")])
    svc, _ = _svc(tmp_path, [_owned("auth-a", REPO_A), _owned("auth-b", REPO_B)], cfg)
    svc.refresh_and_list_all(force=True)
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-a", "auth-b"}

    cfg.source_repos.repos[0].enabled = False
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-b"}
    assert svc.load_entry("auth-a", "e1") is None  # 禁用后不可载入

    cfg.source_repos.repos[0].enabled = True  # 快照保留：重新启用即恢复
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-a", "auth-b"}


def test_remove_disabled_repo_clears_snapshots(tmp_path) -> None:
    """回归：先禁用再删除，联邦反查不到 repo_id，也必须按快照归属清干净。"""
    cfg = _repo_cfg([(REPO_A, True, "verified")])
    svc, _ = _svc(tmp_path, [_owned("auth-a", REPO_A)], cfg)
    svc.refresh_and_list_all(force=True)
    cfg.source_repos.repos[0].enabled = False
    svc.remove_repo("", REPO_A)  # federation 已反查不到 repo_id
    assert svc._store.list_all() == []


def test_unsubscribed_orphans_are_purged(tmp_path) -> None:
    """配置里已没有的订阅留下的快照（旧版本漏清的僵尸组）读取时自动清理。"""
    cfg = _repo_cfg([(REPO_A, True, "verified"), (REPO_B, True, "verified")])
    svc, _ = _svc(tmp_path, [_owned("auth-a", REPO_A), _owned("auth-b", REPO_B)], cfg)
    svc.refresh_and_list_all(force=True)
    cfg.source_repos.repos.pop(1)
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-a"}
    assert {s["_authority"] for s in svc._store.list_all()} == {"auth-a"}


def test_upstream_dropped_source_is_purged(tmp_path) -> None:
    """订阅仍在、但上游 manifest 移除了某个源 → 其快照清理。"""
    cfg = _repo_cfg([(REPO_A, True, "verified")])
    svc, fed = _svc(
        tmp_path,
        [_owned("auth-a", REPO_A), _owned("auth-a2", REPO_A, entry_id="x")],
        cfg,
    )
    svc.refresh_and_list_all(force=True)
    fed._entries = [_owned("auth-a", REPO_A)]  # 上游删了 auth-a2
    svc.refresh_and_list_all(force=True)
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-a"}


def test_manifest_failure_does_not_purge(tmp_path) -> None:
    """manifest 拉取失败（订阅下一个源都没解析出来）不能误删快照。"""
    cfg = _repo_cfg([(REPO_A, True, "verified")])
    svc, fed = _svc(tmp_path, [_owned("auth-a", REPO_A)], cfg)
    svc.refresh_and_list_all(force=True)
    fed._entries = []  # 整个订阅暂时解析不出来
    svc.refresh_and_list_all(force=True)
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-a"}


def test_blocked_content_hidden_and_not_loadable(tmp_path) -> None:
    cfg = _repo_cfg([(REPO_A, True, "verified")])
    svc, _ = _svc(tmp_path, [_owned("auth-a", REPO_A, content="bad")], cfg)
    svc._federation._entries[0]["content_hash"] = "sha256:bad"
    svc.refresh_and_list_all(force=True)
    assert len(svc.list_cached()) == 1
    cfg.blocked_content_hashes.append("sha256:bad")  # 屏蔽在落盘之后
    assert svc.list_cached() == []
    assert svc.load_entry("auth-a", "e1") is None


def test_untrusted_script_snapshots_hidden(tmp_path) -> None:
    cfg = _repo_cfg([(REPO_A, True, "verified")])
    svc, _ = _svc(
        tmp_path,
        [
            _owned("script-a", REPO_A, source_type="ott-script"),
            _owned("rule-a", REPO_A, entry_id="r1"),
        ],
        cfg,
    )
    svc.refresh_and_list_all(force=True)
    cfg.source_repos.repos[0].trust_state = "unverified"  # 拒绝/撤销信任
    assert {e["_authority"] for e in svc.list_cached()} == {"rule-a"}


def test_refresh_repo_url_materializes_only_that_repo(tmp_path) -> None:
    """添加 / 重新启用订阅后立即物化该订阅（不等下次进入文库）。"""
    cfg = _repo_cfg([(REPO_A, True, "verified"), (REPO_B, True, "verified")])
    svc, fed = _svc(tmp_path, [_owned("auth-a", REPO_A), _owned("auth-b", REPO_B)], cfg)
    svc.refresh_repo_url(REPO_B + "/")
    assert fed.materialize_calls == ["auth-b"]
    assert {e["_authority"] for e in svc.list_cached()} == {"auth-b"}


def test_unknown_authority_failure_message(tmp_path) -> None:
    """源已不在启用订阅中时，失败原因不再误报为「网络不可达」。"""
    from src.backend.integration.source_status_store import SourceStatusStore

    fed = _FakeFederation([])
    status = SourceStatusStore(tmp_path / "status")
    svc = SnapshotCatalogService(
        fed, EntrySnapshotStore(tmp_path), None, status_store=status
    )
    svc.refresh_source("gone")
    assert "不在启用的订阅中" in status.get("gone")["message"]
