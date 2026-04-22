import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..models.dto.text_catalog_item import TextCatalogItem
from .text_source_config import TextSourceConfig, TextSourceEntry


@dataclass
class RuntimeConfig:
    """运行时配置，从 JSON 文件加载。"""

    base_url: str = "http://127.0.0.1:8080"
    api_timeout: float = 20.0

    login_api_url: str = ""
    validate_api_url: str = ""
    refresh_api_url: str = ""
    register_api_url: str = ""

    text_source_config: TextSourceConfig = field(default_factory=TextSourceConfig)
    catalog_items: list[TextCatalogItem] = field(default_factory=list)

    @classmethod
    def load_from_file(cls, config_path: str | None = None) -> "RuntimeConfig":
        if config_path is None:
            config_path = cls._find_config_file()

        if config_path and os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return cls._from_dict(data)

        return cls()

    @classmethod
    def _find_config_file(cls) -> str | None:
        user_config = Path.home() / ".config" / "typetype" / "config.json"
        if user_config.exists():
            return str(user_config)

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
            sources[key] = TextSourceEntry(
                key=key,
                label=source_data.get("label", key),
                local_path=source_data.get("local_path"),
                has_ranking=source_data.get("has_ranking", False),
            )
            if not default_key:
                default_key = key

        text_source_config = TextSourceConfig(
            default_key=data.get("default_text_source_key", default_key),
            sources=sources,
        )

        return cls(
            base_url=base_url,
            api_timeout=api_timeout,
            text_source_config=text_source_config,
        )

    def __post_init__(self):
        if not self.login_api_url:
            self.login_api_url = f"{self.base_url}/api/v1/auth/login"
        if not self.validate_api_url:
            self.validate_api_url = f"{self.base_url}/api/v1/users/me"
        if not self.refresh_api_url:
            self.refresh_api_url = f"{self.base_url}/api/v1/auth/refresh"
        if not self.register_api_url:
            self.register_api_url = f"{self.base_url}/api/v1/auth/register"

    @property
    def default_text_source_key(self) -> str:
        return self.text_source_config.default_key

    def get_text_source(self, key: str | None = None) -> TextSourceEntry | None:
        k = key or self.default_text_source_key
        return self.text_source_config.get_source(k)

    def get_text_source_options(self) -> list[dict[str, str]]:
        options = self.text_source_config.get_source_options()
        options.extend(
            {"key": item.text_id, "label": item.label} for item in self.catalog_items
        )
        return options

    def get_ranking_sources(self) -> list[TextSourceEntry]:
        return self.text_source_config.get_ranking_sources()

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        self.catalog_items = items

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 并持久化到 config.json。

        同时重新计算派生的 API URL。
        """
        new_base_url = new_base_url.rstrip("/")
        self.base_url = new_base_url
        self.login_api_url = f"{new_base_url}/api/v1/auth/login"
        self.validate_api_url = f"{new_base_url}/api/v1/users/me"
        self.refresh_api_url = f"{new_base_url}/api/v1/auth/refresh"
        self.register_api_url = f"{new_base_url}/api/v1/auth/register"
        self._save_to_file()

    def _save_to_file(self) -> None:
        """将当前配置持久化到 config.json。"""
        config_path = self._find_config_file()
        if not config_path:
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            data["base_url"] = self.base_url
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
