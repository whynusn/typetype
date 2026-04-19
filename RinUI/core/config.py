import json
import platform
import sys
from enum import Enum
from pathlib import Path


def is_win11():
    return bool(
        is_windows()
        and (
            platform.release() >= "10"
            and int(platform.version().split(".")[2]) >= 22000
        )
    )


def is_win10():
    return bool(
        is_windows()
        and (
            platform.release() >= "10"
            and int(platform.version().split(".")[2]) >= 10240
        )
    )


def is_windows():
    return platform.system() == "Windows"


def resource_path(relative_path):
    """兼容 PyInstaller 打包和开发环境的路径"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(relative_path).resolve()


rinui_core_path = Path(__file__).resolve().parent  # RinUI/core 目录

BASE_DIR = Path.cwd().resolve()
APP_CONFIG_PATH = BASE_DIR / "config"
RINUI_PATH = resource_path(
    rinui_core_path.parent.parent
)  # 使用 resource_path 处理路径，等同 ../../

DEFAULT_CONFIG = {
    "theme": {
        "current_theme": "Auto",
    },
    "win10_feat": {
        "backdrop_light": 0xA6FFFFFF,
        "backdrop_dark": 0xA6000000,
    },
    "theme_color": "#605ed2",
    "backdrop_effect": "mica" if is_win11() else "acrylic" if is_win10() else "none",
}


class Theme(Enum):
    Auto = "Auto"
    Dark = "Dark"
    Light = "Light"


class BackdropEffect(Enum):
    None_ = "none"
    Acrylic = "acrylic"
    Mica = "mica"
    Tabbed = "tabbed"


class AppUIConfigManager:
    """应用层 UI 配置管理器，读写 config/config.json 的 ui 字段。

    所有运行时修改（主题切换等）都写入 config/config.json 的 ui 字段，
    不修改 RinUI 文件夹内容。
    """

    def __init__(self, config_path: Path, defaults: dict):
        self._config_path = Path(config_path)
        self._defaults = defaults
        self.config: dict = {}
        self._full_app_config: dict = {}
        self.load()

    def load(self) -> None:
        """加载配置：优先从 config/config.json 的 ui 字段读取，回退到默认值。"""
        if self._config_path.exists():
            try:
                with self._config_path.open(encoding="utf-8") as f:
                    self._full_app_config = json.load(f)
                self.config = self._full_app_config.get("ui", {})
            except Exception:
                self.config = {}
        # 用默认值补齐缺失的键
        self._merge_defaults()
        if not self.config:
            self.save_config()

    def _merge_defaults(self) -> None:
        """用默认值填充缺失的配置键（不覆盖已有值）。"""
        import copy

        merged = copy.deepcopy(self._defaults)
        self._deep_merge(merged, self.config)
        self.config = merged

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """将 override 中的值合并到 base，override 优先。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                AppUIConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value

    def save_config(self) -> None:
        """将 UI 配置写回 config/config.json 的 ui 字段。"""
        try:
            # 先读取完整的应用配置文件
            if self._config_path.exists():
                with self._config_path.open(encoding="utf-8") as f:
                    self._full_app_config = json.load(f)
            else:
                self._full_app_config = {}

            # 更新 ui 字段
            self._full_app_config["ui"] = self.config

            # 确保目录存在
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            with self._config_path.open("w", encoding="utf-8") as f:
                json.dump(self._full_app_config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving UI config: {e}")

    def __getitem__(self, key: str):
        return self.config.get(key)

    def __setitem__(self, key: str, value) -> None:
        self.config[key] = value
        self.save_config()

    def __repr__(self) -> str:
        return json.dumps(self.config, ensure_ascii=False, indent=4)


# 应用层 UI 配置（读写 config/config.json 的 ui 字段）
AppUIConfig = AppUIConfigManager(
    config_path=APP_CONFIG_PATH / "config.json",
    defaults=DEFAULT_CONFIG,
)
