"""RegistryAdapter：开源文库条目加载 = 同步显示快照存储 + 后台 revalidate。

核心语义（2026-08-14）：进入开源文库视图永远等于当前快照存储——
同步 `list_cached()` 零网络即时显示，随后后台非强制重新物化过期源并
原地更新列表（不置 loading、不白屏）；后台失败不影响已显示的快照视图。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.backend.presentation.adapters.registry_adapter import RegistryAdapter


class DummyThreadPool:
    """捕获被 start 的 worker，不真正执行（确定性测试）。"""

    def __init__(self) -> None:
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter(catalog=None):
    federation = MagicMock()
    manifest_cache = MagicMock()
    adapter = RegistryAdapter(federation, manifest_cache, catalog=catalog)
    pool = DummyThreadPool()
    adapter._thread_pool = pool
    return adapter, pool


def test_load_federated_entries_shows_store_then_schedules_revalidate():
    """进入开源文库：同步立即显示当前已存快照，并排队后台 revalidate。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = [
        {"entry_id": "e1", "_authority": "a1", "content": "c1", "freshness": "fresh"}
    ]
    catalog.refresh_and_list_all.return_value = [
        {"entry_id": "e1", "_authority": "a1", "content": "c1", "freshness": "fresh"}
    ]
    adapter, pool = _build_adapter(catalog=catalog)

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)

    adapter.loadFederatedEntries()

    # 同步 emit 当前已存快照（零网络，federation 不被触碰）
    assert len(loaded) == 1
    assert loaded[0][0]["entry_id"] == "e1"
    assert adapter.entries_loading is False  # 不置 loading、不白屏
    federation = adapter._federation
    federation.list_all_entries.assert_not_called()
    # 后台 revalidate 已排队（非强制：refresh_and_list_all 默认 force=False）
    assert len(pool.started_workers) == 1


def test_revalidate_stacked_skipped_while_running():
    """后台 revalidate 进行中再次进入不叠加（防重复网络/重复 emit）。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = []
    adapter, pool = _build_adapter(catalog=catalog)

    adapter.loadFederatedEntries()
    assert len(pool.started_workers) == 1
    # 第一次 revalidate 仍在进行中（worker 未完成）
    adapter.loadFederatedEntries()
    assert len(pool.started_workers) == 1


def test_revalidate_failure_keeps_store_view():
    """后台 revalidate 失败不发射 entriesLoadFailed（保持已显示的快照视图）。"""
    adapter, _ = _build_adapter(catalog=MagicMock())
    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter._entries_revalidating = True
    adapter._on_entries_revalidate_failed("网络超时")

    assert adapter._entries_revalidating is False
    assert failed == []  # 失败静默：视图仍为当前快照存储


def test_preview_manifest_runs_in_worker_and_emits_result():
    adapter, pool = _build_adapter()
    adapter._federation.preview_manifest.return_value = {
        "url": "https://example.test/repo.json",
        "type": "repository",
    }
    results: list[dict] = []
    adapter.repoManifestPreviewed.connect(results.append)

    result = adapter.previewRepoManifest("https://example.test/repo.json")

    assert result == {"url": "https://example.test/repo.json", "pending": True}
    assert adapter._federation.preview_manifest.call_count == 0
    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()
    assert results == [adapter._federation.preview_manifest.return_value]


def test_load_federated_entries_without_catalog_falls_back_to_federation():
    """未装配 catalog（旧路径）：退化为 federation 全量列表。"""
    federation = MagicMock()
    federation.list_all_entries.return_value = [{"entry_id": "x"}]
    adapter, pool = _build_adapter(catalog=None)
    adapter._federation = federation

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)

    adapter.loadFederatedEntries()

    assert len(loaded) == 1
    assert loaded[0][0]["entry_id"] == "x"


def test_refresh_repo_scoped_to_single_repo():
    """订阅源组头刷新按组件层级作用域：只物化该 repo（refresh_repo + list_cached）。

    回归：旧实现物化后调用 refresh_and_list_all()，会重新物化其他源
    （缓存冷时打网络）并把所有源快照 captured_at 重置（freshness 徽章
    被污染）；现在视图走 list_cached() 纯读，其他 repo 零调用。
    """
    catalog = MagicMock()
    catalog.list_cached.return_value = [
        {"entry_id": "e1", "_authority": "a1", "content": "c1", "freshness": "fresh"}
    ]
    adapter, pool = _build_adapter(catalog=catalog)

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)

    adapter.refreshRepoEntries("repo-1")

    # 刷新期间：只标记 repo（组头动画），不置列表级 loading（动画不覆盖整列表）
    assert adapter.refreshing_repo == "repo-1"
    assert adapter.entries_loading is False

    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()  # 同步执行 worker 任务

    # 只物化该 repo + 纯读快照视图
    catalog.refresh_repo.assert_called_once_with("repo-1")
    catalog.list_cached.assert_called_once_with()
    # 其他 repo 零物化调用：绝不触发全量列源
    catalog.refresh_and_list_all.assert_not_called()
    adapter._federation.list_all_entries.assert_not_called()
    # 视图 = 当前全部已存快照；完成后组头动画标记清除、列表退出 loading
    assert loaded[-1][0]["entry_id"] == "e1"
    assert adapter.refreshing_repo == ""
    assert adapter.entries_loading is False


def test_refresh_repo_failure_clears_group_animation_marker():
    """repo 刷新失败同样清除组头动画标记（动画不残留）。"""
    catalog = MagicMock()
    catalog.list_cached.side_effect = RuntimeError("boom")
    adapter, pool = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshRepoEntries("repo-1")
    assert adapter.refreshing_repo == "repo-1"
    assert adapter.entries_loading is False  # repo 刷新不触发列表级 loading

    pool.started_workers[0].run()

    assert len(failed) == 1
    assert adapter.refreshing_repo == ""


def test_refresh_all_clears_group_animation_marker():
    """列表级刷新接管一切：清除可能残留的源组头动画标记。"""
    catalog = MagicMock()
    catalog.refresh_and_list_all.return_value = []
    adapter, pool = _build_adapter(catalog=catalog)

    adapter._refreshing_repo = "repo-1"  # 模拟 repo 刷新进行中
    adapter.refreshAllSources()

    assert adapter.refreshing_repo == ""
    assert adapter.entries_loading is True  # 列表级刷新置列表级 loading
    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()
    assert adapter.entries_loading is False


# ----------------------------------------------------------------------
# 刷新硬超时兜底（worker 卡死时状态必须清理，动画/loading 不能永转）
# ----------------------------------------------------------------------


def test_refresh_repo_timeout_clears_marker_and_emits_failure():
    """repo 刷新 worker 卡死（网络 hang）超时：清组头动画标记 + 列表 loading + 报错。"""
    catalog = MagicMock()
    adapter, pool = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshRepoEntries("repo-1")
    assert adapter.refreshing_repo == "repo-1"
    assert len(pool.started_workers) == 1
    # worker 永不完成（卡死）；模拟 45s 超时到期
    adapter._on_refresh_timeout()

    assert adapter.refreshing_repo == ""  # 动画必须停
    assert adapter.entries_loading is False
    assert failed == ["刷新超时，请检查网络"]


def test_refresh_all_timeout_clears_loading_and_emits_failure():
    """总刷新卡死超时：清列表级 loading + 报错（旧实现同款提示）。"""
    catalog = MagicMock()
    adapter, _ = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshAllSources()
    assert adapter.entries_loading is True
    adapter._on_refresh_timeout()

    assert adapter.entries_loading is False
    assert failed == ["刷新超时，请检查网络"]


def test_revalidate_timeout_quiet_keeps_view():
    """后台 revalidate 卡死超时：静默（不发错误信号，保持快照视图）。"""
    catalog = MagicMock()
    adapter, pool = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter._revalidate_entries()
    assert adapter._entries_revalidating is True
    adapter._on_revalidate_timeout()

    assert adapter._entries_revalidating is False
    assert failed == []  # 后台超时静默


def test_refresh_timeout_stale_ignored_when_idle():
    """操作已提前完成（worker 正常结束）→ 陈旧定时器到点必须忽略（不误报）。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = []
    adapter, pool = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshRepoEntries("repo-1")
    pool.started_workers[0].run()  # worker 正常完成（状态全部清理）
    assert adapter.refreshing_repo == ""
    adapter._on_refresh_timeout()  # 陈旧超时

    assert failed == []  # 不误报
    assert adapter.refreshing_repo == ""


def test_refresh_repo_without_catalog_falls_back_to_full_list():
    """未装配 catalog（旧路径）：repo 刷新退化为全量列表。"""
    federation = MagicMock()
    federation.list_all_entries.return_value = [{"entry_id": "x"}]
    adapter, pool = _build_adapter(catalog=None)
    adapter._federation = federation

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)

    adapter.refreshRepoEntries("repo-1")

    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()

    assert loaded[-1][0]["entry_id"] == "x"


def test_remove_repo_clears_snapshots_of_its_authorities():
    """删除订阅连带清理该 repo 下全部 authority 的快照残留（防孤儿目录）。"""
    catalog = MagicMock()
    federation = MagicMock()
    federation.repo_id_of_url.return_value = "repo-1"
    adapter, _ = _build_adapter(catalog=catalog)
    adapter._federation = federation
    adapter._runtime_config = MagicMock()
    adapter._runtime_config.remove_source_repo.return_value = True

    adapter.removeRepo("https://example.com/ott-repo.json")

    federation.repo_id_of_url.assert_called_once_with(
        "https://example.com/ott-repo.json"
    )
    catalog.remove_repo.assert_called_once_with("repo-1")


# ----------------------------------------------------------------------
# 源（authority）级刷新 + 刷新失败反馈（2026-08-15）
# ----------------------------------------------------------------------


def _run_first_worker(pool):
    pool.started_workers[0].run()


def test_refresh_source_entries_refreshes_authority_and_clears_marker():
    """源级刷新：只走 catalog.refresh_source(该 authority)，动画标记完成即清。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = [{"entry_id": "e1", "_authority": "a1"}]
    catalog.last_refresh_ok = ["a1"]
    catalog.last_refresh_failed = []
    adapter, pool = _build_adapter(catalog=catalog)

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)
    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshSourceEntries("a1")

    assert adapter.refreshing_authority == "a1"
    assert len(pool.started_workers) == 1
    _run_first_worker(pool)

    catalog.refresh_source.assert_called_once_with("a1")
    assert loaded[-1][0]["entry_id"] == "e1"
    assert adapter.refreshing_authority == ""  # 完成即清（动画结束）
    assert failed == []  # 全成功不报错


def test_refresh_source_entries_all_failed_reports_source_scoped_status():
    """源级刷新全部失败：只发源状态，不盖整列表（全局错误保持为空）。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = [{"entry_id": "old", "_authority": "a1"}]
    catalog.last_refresh_ok = []
    catalog.last_refresh_failed = ["a1"]
    adapter, pool = _build_adapter(catalog=catalog)

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)
    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)
    statuses: list[tuple[str, dict]] = []
    adapter.sourceStatusChanged.connect(
        lambda authority, status: statuses.append((authority, status))
    )

    adapter.refreshSourceEntries("a1")
    _run_first_worker(pool)

    assert loaded[-1][0]["entry_id"] == "old"  # 视图 = 缓存快照
    assert failed == []  # 源级失败不发射全局错误 → 列表不被错误页替换
    assert len(statuses) == 1
    assert statuses[0][0] == "a1"
    assert statuses[0][1]["state"] == "failed"
    assert "缓存快照" in statuses[0][1]["message"]  # 明确告知刷新未成功


def test_refresh_source_entries_success_emits_ok_status():
    """源级刷新成功也发 ok 状态（组头健康芯片的数据源）。"""
    catalog = MagicMock()
    catalog.list_cached.return_value = [{"entry_id": "e1", "_authority": "a1"}]
    catalog.last_refresh_ok = ["a1"]
    catalog.last_refresh_failed = []
    adapter, pool = _build_adapter(catalog=catalog)

    statuses: list[tuple[str, dict]] = []
    adapter.sourceStatusChanged.connect(
        lambda authority, status: statuses.append((authority, status))
    )
    adapter.refreshSourceEntries("a1")
    _run_first_worker(pool)

    assert statuses[0][0] == "a1"
    assert statuses[0][1]["state"] == "ok"


def test_refresh_all_sources_partial_failure_keeps_list_silent():
    """总刷新部分失败：列表正常更新，不弹错误态（日志提示即可）。"""
    catalog = MagicMock()
    catalog.refresh_and_list_all.return_value = [
        {"entry_id": "new", "_authority": "a1"}
    ]
    catalog.last_refresh_ok = ["a1"]
    catalog.last_refresh_failed = ["a2"]
    adapter, pool = _build_adapter(catalog=catalog)

    loaded: list[list[dict]] = []
    adapter.entriesLoaded.connect(loaded.append)
    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshAllSources()
    assert adapter.entries_loading is True
    _run_first_worker(pool)

    assert adapter.entries_loading is False
    assert loaded[-1][0]["entry_id"] == "new"
    assert failed == []  # 部分失败不盖错误态


def test_refresh_all_sources_all_failed_reports_error():
    """总刷新全部失败（断网）：报错并说明当前为缓存快照。"""
    catalog = MagicMock()
    catalog.refresh_and_list_all.return_value = [
        {"entry_id": "old", "_authority": "a1"}
    ]
    catalog.last_refresh_ok = []
    catalog.last_refresh_failed = ["a1", "a2"]
    adapter, pool = _build_adapter(catalog=catalog)

    failed: list[str] = []
    adapter.entriesLoadFailed.connect(failed.append)

    adapter.refreshAllSources()
    _run_first_worker(pool)

    assert failed and "缓存快照" in failed[0]
