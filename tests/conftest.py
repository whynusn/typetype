"""Pytest 全局隔离：避免测试写操作污染真实用户配置。

`RuntimeConfig` 未绑定 `_config_path` 时，`_save_to_file()` / `load_from_file()` /
`ensure_user_config_exists()` 回退到 `user_config_path()`（真实
`~/.config/typetype/config.json`）。测试若直接构造 `RuntimeConfig()` 并调用
`add_source_repo` / `update_*` 等写方法，会把测试数据写入真实配置（2026-08-13
实测污染：运行测试后真实 config 被写入 example.org 订阅）。

本 autouse fixture 将 `runtime_config` 模块命名空间内的
`user_config_path` / `user_config_dir` 重定向到每个测试独立的临时目录，
从根上隔离。显式断言这两个函数本身的测试（tests/test_app_paths.py）直接调用
`app_paths.user_config_path()`，不受本 fixture 影响。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """将所有测试中的用户配置读写重定向到临时目录。"""
    config_dir = tmp_path / "typetype-config"
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_path",
        lambda: config_dir / "config.json",
    )
    monkeypatch.setattr(
        "src.backend.config.runtime_config.user_config_dir",
        lambda: config_dir,
    )
