"""UpdateAdapter 测试（ADR-014 Wave 2 Lane F）。

不发起真实网络、不真实替换目录：UpdateChecker 全程 mock，
安装步骤（解压/updater 调用）monkeypatch 为 no-op。

接口约定与 Lane E（update_checker.py）对齐：
- check_for_update() -> UpdateInfo | None（含 version / assets）
- download(url, sha256, dest) -> bool
- build_download_candidates(tag, asset, mirrors) -> list[str]
"""

import sys
import time

import pytest
from unittest.mock import MagicMock

from src.backend.presentation.adapters.update_adapter import (
    UpdateAdapter,
    _PLATFORM_ASSETS,
)
from src.backend.workers.update_worker import UpdateWorker


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker):
        self.started_workers.append(worker)


def _build_adapter(mirrors=None):
    checker = MagicMock()
    config = MagicMock()
    config.update.mirrors = mirrors or []
    config.update.check_interval_hours = 24
    adapter = UpdateAdapter(update_checker=checker, runtime_config=config)
    adapter._thread_pool = DummyThreadPool()
    return adapter, checker


@pytest.fixture(autouse=True)
def _reset_throttle():
    UpdateWorker.last_check_at = 0.0
    yield
    UpdateWorker.last_check_at = 0.0


# ---------------------------------------------------------------------------
# 检查：check_now / start_auto_check
# ---------------------------------------------------------------------------


def test_check_now_with_new_version_emits_signal():
    adapter, checker = _build_adapter()
    results = []
    adapter.checkFinished.connect(
        lambda available, version, error: results.append((available, version, error))
    )
    info = MagicMock()
    info.version = "1.2.3"
    checker.check_for_update.return_value = info

    adapter.check_now()
    worker = adapter._thread_pool.started_workers[0]
    worker.run()

    assert results == [(True, "1.2.3", "")]
    assert adapter.available_version == "1.2.3"


def test_check_now_no_update_emits_not_available():
    adapter, checker = _build_adapter()
    results = []
    adapter.checkFinished.connect(
        lambda available, version, error: results.append((available, version, error))
    )
    checker.check_for_update.return_value = None

    adapter.check_now()
    worker = adapter._thread_pool.started_workers[0]
    worker.run()

    assert results == [(False, "", "")]
    assert adapter.available_version == ""


def test_check_now_error_propagates_to_ui():
    adapter, checker = _build_adapter()
    results = []
    adapter.checkFinished.connect(
        lambda available, version, error: results.append((available, version, error))
    )
    checker.check_for_update.side_effect = RuntimeError("网络不可用")

    adapter.check_now()
    worker = adapter._thread_pool.started_workers[0]
    worker.run()

    assert results == [(False, "", "网络不可用")]


def test_auto_check_error_is_silent():
    adapter, checker = _build_adapter()
    results = []
    adapter.checkFinished.connect(
        lambda available, version, error: results.append((available, version, error))
    )
    checker.check_for_update.side_effect = RuntimeError("网络不可用")

    adapter.start_auto_check()
    worker = adapter._thread_pool.started_workers[0]
    worker.run()

    # 自动检查失败静默：error 为空串
    assert results == [(False, "", "")]


def test_auto_check_throttled_skips():
    adapter, checker = _build_adapter()
    results = []
    adapter.checkFinished.connect(
        lambda available, version, error: results.append((available, version, error))
    )
    checker.check_for_update.return_value = None
    # 置最近检查时间为「现在」，未满间隔应跳过
    UpdateWorker.last_check_at = time.monotonic()

    adapter.start_auto_check()
    worker = adapter._thread_pool.started_workers[0]
    worker.run()

    checker.check_for_update.assert_not_called()
    assert results == [(False, "", "")]


# ---------------------------------------------------------------------------
# 下载与安装：镜像 fallback / sha256 丢弃 / 平台无资产
# ---------------------------------------------------------------------------


def _mock_install_steps(adapter):
    """mock 安装步骤（不真实解压/替换目录）。"""
    adapter._install_dir = MagicMock(return_value="/tmp/typetype-install")
    adapter._extract_archive = MagicMock()
    adapter._run_updater = MagicMock()


def _run_install(adapter, checker, version="2.0.0"):
    _mock_install_steps(adapter)
    checker.check_for_update.return_value.assets = [
        {"name": _PLATFORM_ASSETS["linux"], "url": "x", "sha256": "abc"}
    ]
    adapter._do_download_and_install(version)


def test_mirror_fallback_when_first_source_fails():
    adapter, checker = _build_adapter()
    # 直链抛异常（首源失败）→ 换镜像
    checker.download.side_effect = [RuntimeError("download failed"), True]
    checker.build_download_candidates.return_value = [
        "https://github.com/.../direct",
        "https://mirror.example.com/typetype",
    ]

    _run_install(adapter, checker)

    urls = [call.args[0] for call in checker.download.call_args_list]
    assert urls == [
        "https://github.com/.../direct",
        "https://mirror.example.com/typetype",
    ]
    adapter._run_updater.assert_called_once()


def test_sha256_failure_discards_and_tries_next():
    adapter, checker = _build_adapter()
    # 首源 sha256 校验失败（返回 False）→ 丢弃换下一个
    checker.download.side_effect = [False, True]
    checker.build_download_candidates.return_value = [
        "https://a.example/typetype-linux-amd64.tar.gz",
        "https://b.example/typetype-linux-amd64.tar.gz",
    ]

    _run_install(adapter, checker)

    urls = [call.args[0] for call in checker.download.call_args_list]
    assert urls == [
        "https://a.example/typetype-linux-amd64.tar.gz",
        "https://b.example/typetype-linux-amd64.tar.gz",
    ]


def test_all_sources_fail_raises():
    adapter, checker = _build_adapter()
    checker.download.return_value = False
    checker.build_download_candidates.return_value = [
        "https://a.example/x",
        "https://b.example/x",
    ]

    with pytest.raises(RuntimeError, match="所有下载源均失败"):
        _run_install(adapter, checker)


def test_platform_without_asset_raises(monkeypatch):
    adapter, checker = _build_adapter()
    monkeypatch.setattr(sys, "platform", "freebsd")
    with pytest.raises(RuntimeError, match="当前平台暂无可更新产物"):
        adapter._do_download_and_install("2.0.0")


def test_platform_asset_mapping():
    assert _PLATFORM_ASSETS["linux"] == "typetype-linux-amd64.tar.gz"
    assert _PLATFORM_ASSETS["win32"] == "typetype-windows-amd64.zip"
    assert _PLATFORM_ASSETS["darwin"] == "typetype-macos.zip"


def test_sha256_read_from_update_info_assets():
    adapter, checker = _build_adapter()
    checker.check_for_update.return_value.assets = [
        {"name": "typetype-linux-amd64.tar.gz", "sha256": "deadbeef"}
    ]

    sha = adapter._asset_sha256("2.0.0", "typetype-linux-amd64.tar.gz")

    assert sha == "deadbeef"


def test_mirrors_passed_to_build_candidates():
    adapter, checker = _build_adapter(mirrors=["https://m1.example"])
    checker.build_download_candidates.return_value = ["https://direct/x"]
    checker.check_for_update.return_value.assets = []
    checker.download.return_value = True

    _run_install(adapter, checker)

    checker.build_download_candidates.assert_called_once_with(
        "2.0.0",
        "typetype-linux-amd64.tar.gz",
        ["https://m1.example"],
    )


def test_empty_mirrors_pass_none_to_use_builtin_defaults():
    adapter, checker = _build_adapter()  # mirrors 为空
    checker.build_download_candidates.return_value = ["https://direct/x"]
    checker.check_for_update.return_value.assets = []
    checker.download.return_value = True

    _run_install(adapter, checker)

    checker.build_download_candidates.assert_called_once_with(
        "2.0.0", "typetype-linux-amd64.tar.gz", None
    )


def test_download_progress_emits_percent():
    adapter, checker = _build_adapter()
    percents = []
    adapter.downloadProgress.connect(percents.append)

    adapter._on_progress(50, 200)

    assert percents == [25]


def test_dismiss_clears_state():
    adapter, checker = _build_adapter()
    adapter._available_version = "9.9.9"
    statuses = []
    adapter.statusChanged.connect(statuses.append)

    adapter.dismiss()

    assert adapter.available_version == ""
    assert statuses == [""]
