"""Platform-specific writable application paths."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

APP_NAME = "TypeType"
LINUX_DIR_NAME = "typetype"


def _user_root_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path.home() / ".config" / LINUX_DIR_NAME


def user_config_dir() -> Path:
    return _user_root_dir()


def user_data_dir() -> Path:
    system = platform.system()
    if system in {"Darwin", "Windows"}:
        return _user_root_dir()
    return Path.home() / ".local" / "share" / LINUX_DIR_NAME


def user_config_path() -> Path:
    return user_config_dir() / "config.json"


def user_texts_dir() -> Path:
    return user_data_dir() / "texts"


def user_ziti_dir() -> Path:
    return user_data_dir() / "ziti"


def user_trainer_dir() -> Path:
    return user_data_dir() / "trainer"


def user_fonts_dir() -> Path:
    return user_data_dir() / "fonts"


def ensure_user_texts_seeded(source_dir: Path | None = None) -> int:
    """Copy bundled text files into the writable user texts directory.

    Existing user files are never overwritten. Returns the number of copied files.
    """
    if source_dir is None:
        source_dir = Path(__file__).resolve().parents[3] / "resources" / "texts"
    if not source_dir.exists():
        return 0

    target_dir = user_texts_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_file in sorted(source_dir.glob("*.txt")):
        target_file = target_dir / source_file.name
        if target_file.exists():
            continue
        shutil.copy2(source_file, target_file)
        copied += 1
    return copied


def ensure_user_ziti_seeded(source_dir: Path | None = None) -> int:
    """Copy bundled ZiTi scheme files into the writable user ZiTi directory."""
    if source_dir is None:
        source_dir = Path(__file__).resolve().parents[3] / "resources" / "ziti"
    if not source_dir.exists():
        return 0

    target_dir = user_ziti_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_file in sorted(source_dir.glob("*.txt")):
        target_file = target_dir / source_file.name
        if target_file.exists():
            continue
        shutil.copy2(source_file, target_file)
        copied += 1
    return copied


def ensure_user_trainer_seeded(source_dir: Path | None = None) -> int:
    """Copy bundled trainer lexicons into the writable user trainer directory."""
    if source_dir is None:
        source_dir = Path(__file__).resolve().parents[3] / "resources" / "trainer"
    if not source_dir.exists():
        return 0

    target_dir = user_trainer_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_file in sorted(source_dir.glob("*.txt")):
        target_file = target_dir / source_file.name
        if target_file.exists():
            continue
        shutil.copy2(source_file, target_file)
        copied += 1
    return copied


def ensure_user_fonts_seeded(source_dir: Path | None = None) -> int:
    """Copy bundled font files into the writable user fonts directory.

    Existing user files are never overwritten. Returns the number of copied files.
    """
    if source_dir is None:
        source_dir = Path(__file__).resolve().parents[3] / "resources" / "fonts"
    if not source_dir.exists():
        return 0

    target_dir = user_fonts_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_file in sorted(source_dir.glob("*.ttf")):
        target_file = target_dir / source_file.name
        if target_file.exists():
            continue
        shutil.copy2(source_file, target_file)
        copied += 1
    for source_file in sorted(source_dir.glob("*.otf")):
        target_file = target_dir / source_file.name
        if target_file.exists():
            continue
        shutil.copy2(source_file, target_file)
        copied += 1
    return copied


def char_stats_db_path() -> Path:
    return user_data_dir() / "char_stats.db"


def typing_totals_path() -> Path:
    return user_data_dir() / "typing_totals.json"


def typing_history_path() -> Path:
    return user_data_dir() / "typing_history.json"


def score_retry_db_path() -> Path:
    """成绩重试队列 SQLite 数据库路径。"""
    return user_data_dir() / "score_retry.db"


def slice_metrics_prefs_path() -> Path:
    return user_data_dir() / "slice_metrics_prefs.json"


def text_slice_progress_path() -> Path:
    return user_data_dir() / "text_slice_progress.json"


def user_indexes_dir() -> Path:
    return user_data_dir() / "indexes"


def registry_cache_dir() -> Path:
    return user_data_dir() / "registry_cache"


def builtin_ott_repo_dir() -> Path:
    """内置默认 OTT Repo 目录（打包在应用资源中，离线 fallback 用）。"""
    return Path(__file__).resolve().parents[3] / "resources" / "ott-repo"


def builtin_ott_repo_url() -> str:
    """内置默认 OTT Repo manifest 的 file:// URL。"""
    return (builtin_ott_repo_dir() / "ott-repo.json").as_uri()


def default_ott_hub_url() -> str:
    """默认 OTT 源仓库（hub）manifest URL。

    使用 jsDelivr CDN 而非 raw.githubusercontent.com——raw 直连在国内网络
    常超时（2026-08-13 实测 HTTP 000）。旧 raw URL 订阅由
    ``RepoManifestCache`` 的 jsDelivr 降级兜底（_fetch_manifest_with_mirrors）。
    全新安装首次启动自动订阅；已存在用户配置不自动添加（尊重既有选择）。
    """
    return "https://cdn.jsdelivr.net/gh/whynusn/ott-source-hub@main/ott-repo.json"


def load_common_chars() -> list[str]:
    """加载高频五百中文汉字，用于启动时预热 char_stats 缓存。"""
    try:
        path = (
            Path(__file__).resolve().parents[3] / "resources" / "texts" / "前五百.txt"
        )
        text = path.read_text(encoding="gbk")
        return list(dict.fromkeys(c for c in text if "一" <= c <= "鿿"))
    except Exception:
        return []
