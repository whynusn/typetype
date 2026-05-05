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
