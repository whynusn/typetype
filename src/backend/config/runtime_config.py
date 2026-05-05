import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..models.dto.text_catalog_item import TextCatalogItem
from .app_paths import user_config_path
from .text_source_config import TextSourceConfig, TextSourceEntry


@dataclass
class WenlaiConfig:
    """晴发文服务配置。"""

    base_url: str = "https://qingfawen.fcxxz.com"
    length: int = 0
    difficulty_level: int = 0
    category: str = ""
    segment_mode: str = "manual"
    strict_length: bool = False
    username: str = ""
    display_name: str = ""
    user_id: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            self.base_url = "https://qingfawen.fcxxz.com"
        if not isinstance(self.category, str):
            self.category = ""
        if not isinstance(self.segment_mode, str):
            self.segment_mode = "manual"
        if not isinstance(self.username, str):
            self.username = ""
        if not isinstance(self.display_name, str):
            self.display_name = ""
        self.base_url = self.base_url.rstrip("/")
        if self.length < 0:
            self.length = 0
        if self.difficulty_level < 0:
            self.difficulty_level = 0
        if self.segment_mode not in {"manual", "auto"}:
            self.segment_mode = "manual"


@dataclass
class RuntimeConfig:
    """运行时配置，从 JSON 文件加载。"""

    base_url: str = "http://127.0.0.1:8080"
    api_timeout: float = 20.0

    text_source_config: TextSourceConfig = field(default_factory=TextSourceConfig)
    wenlai: WenlaiConfig = field(default_factory=WenlaiConfig)
    catalog_items: list[TextCatalogItem] = field(default_factory=list)
    _config_path: str | None = field(default=None, repr=False)

    @classmethod
    def load_from_file(cls, config_path: str | None = None) -> "RuntimeConfig":
        if config_path is None:
            config_path = cls._find_config_file()

        if config_path and os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            config = cls._from_dict(data)
            config._config_path = config_path
            return config

        return cls(_config_path=str(user_config_path()))

    @classmethod
    def ensure_user_config_exists(cls) -> str:
        """Ensure the writable user config exists and return its path."""
        target = user_config_path()
        if target.exists():
            return str(target)

        source = cls._find_project_config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        if source and os.path.exists(source):
            shutil.copy2(source, target)
        else:
            with target.open("w", encoding="utf-8") as f:
                json.dump(cls()._to_dict(), f, ensure_ascii=False, indent=4)
        return str(target)

    @classmethod
    def _find_config_file(cls) -> str | None:
        user_config = user_config_path()
        if user_config.exists():
            return str(user_config)

        return cls._find_project_config_file()

    @classmethod
    def _find_project_config_file(cls) -> str | None:
        current = Path(__file__).parent
        while current.parent != current:
            project_config = current / "config" / "config.json"
            if project_config.exists():
                return str(project_config)
            example_config = current / "config" / "config.example.json"
            if example_config.exists():
                return str(example_config)
            current = current.parent

        return None

    @classmethod
    def _from_dict(cls, data: dict) -> "RuntimeConfig":
        base_url = data.get("base_url", "http://127.0.0.1:8080")
        api_timeout = data.get("api_timeout", 20.0)

        sources_data = data.get("text_sources", {})
        sources = {}
        default_key = ""

        for key, source_data in sources_data.items():
            local_path = source_data.get("local_path")
            has_ranking = source_data.get("has_ranking", False)
            sources[key] = TextSourceEntry(
                key=key,
                label=source_data.get("label", key),
                local_path=local_path,
                has_ranking=has_ranking,
                source_type=TextSourceEntry.infer_source_type(local_path, has_ranking),
            )
            if not default_key:
                default_key = key

        text_source_config = TextSourceConfig(
            default_key=data.get("default_text_source_key", default_key),
            sources=sources,
        )
        wenlai_data = data.get("wenlai", {})
        if not isinstance(wenlai_data, dict):
            wenlai_data = {}
        wenlai = WenlaiConfig(
            base_url=cls._safe_str(
                wenlai_data.get("base_url"),
                "https://qingfawen.fcxxz.com",
                allow_empty=False,
            ),
            length=cls._safe_int(wenlai_data.get("length"), 0),
            difficulty_level=cls._safe_int(wenlai_data.get("difficulty_level"), 0),
            category=cls._safe_str(wenlai_data.get("category"), ""),
            segment_mode=cls._safe_str(wenlai_data.get("segment_mode"), "manual"),
            strict_length=bool(wenlai_data.get("strict_length", False)),
            username=cls._safe_str(wenlai_data.get("username"), ""),
            display_name=cls._safe_str(wenlai_data.get("display_name"), ""),
            user_id=cls._safe_int(wenlai_data.get("user_id"), 0),
        )

        return cls(
            base_url=base_url,
            api_timeout=api_timeout,
            text_source_config=text_source_config,
            wenlai=wenlai,
        )

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_str(value, default: str = "", *, allow_empty: bool = True) -> str:
        if not isinstance(value, str):
            return default
        if not allow_empty and not value.strip():
            return default
        return value

    @property
    def default_text_source_key(self) -> str:
        return self.text_source_config.default_key

    def get_text_source(self, key: str | None = None) -> TextSourceEntry | None:
        k = key or self.default_text_source_key
        return self.text_source_config.get_source(k)

    def get_text_source_options(self) -> list[dict[str, str]]:
        options = self.text_source_config.get_source_options()
        options.extend(
            {"key": item.source_key, "label": item.label} for item in self.catalog_items
        )
        return options

    def get_ranking_sources(self) -> list[TextSourceEntry]:
        return self.text_source_config.get_ranking_sources()

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        self.catalog_items = items

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 并持久化到 config.json。"""
        new_base_url = new_base_url.rstrip("/")
        self.base_url = new_base_url
        self._save_to_file()

    def _save_to_file(self) -> None:
        """将当前配置持久化到 config.json。"""
        target_path = user_config_path()
        try:
            source_path = Path(self._config_path) if self._config_path else target_path
            if source_path.exists():
                with source_path.open(encoding="utf-8") as f:
                    data = json.load(f)
            elif target_path.exists():
                with target_path.open(encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = self._to_dict()
            data["base_url"] = self.base_url
            data["wenlai"] = self._to_dict()["wenlai"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self._config_path = str(target_path)
        except Exception:
            pass

    def _to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "default_text_source_key": self.default_text_source_key,
            "api_timeout": self.api_timeout,
            "text_sources": {
                key: {
                    "label": source.label,
                    **({"local_path": source.local_path} if source.local_path else {}),
                    **({"has_ranking": True} if source.has_ranking else {}),
                }
                for key, source in self.text_source_config.sources.items()
            },
            "wenlai": {
                "base_url": self.wenlai.base_url,
                "length": self.wenlai.length,
                "difficulty_level": self.wenlai.difficulty_level,
                "category": self.wenlai.category,
                "segment_mode": self.wenlai.segment_mode,
                "strict_length": self.wenlai.strict_length,
                "username": self.wenlai.username,
                "display_name": self.wenlai.display_name,
                "user_id": self.wenlai.user_id,
            },
        }

    def update_wenlai_config(
        self,
        *,
        base_url: str | None = None,
        length: int | None = None,
        difficulty_level: int | None = None,
        category: str | None = None,
        segment_mode: str | None = None,
        strict_length: bool | None = None,
    ) -> None:
        if base_url is not None:
            self.wenlai.base_url = base_url.rstrip("/")
        if length is not None:
            self.wenlai.length = max(length, 0)
        if difficulty_level is not None:
            self.wenlai.difficulty_level = max(difficulty_level, 0)
        if category is not None:
            self.wenlai.category = category
        if segment_mode is not None:
            self.wenlai.segment_mode = (
                segment_mode if segment_mode in {"manual", "auto"} else "manual"
            )
        if strict_length is not None:
            self.wenlai.strict_length = strict_length
        self._save_to_file()

    def update_wenlai_user(
        self, username: str, display_name: str, user_id: int
    ) -> None:
        self.wenlai.username = username
        self.wenlai.display_name = display_name
        self.wenlai.user_id = user_id
        self._save_to_file()

    def clear_wenlai_user(self) -> None:
        self.wenlai.username = ""
        self.wenlai.display_name = ""
        self.wenlai.user_id = 0
        self._save_to_file()
