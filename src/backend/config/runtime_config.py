import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows 无 fcntl，lockf 在 _save_to_file 中静默降级

from ..models.dto.text_catalog_item import TextCatalogItem
from .app_paths import user_config_path
from ..utils.logger import log_error
from .text_source_config import TextSourceConfig, TextSourceEntry


@dataclass
class WenlaiConfig:
    """晴发文服务配置。

    注意：_safe_int/_safe_str 负责 JSON 类型转换（_from_dict 中调用），
    __post_init__ 负责范围校验。两者分工不同，并非重复。
    """

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
class AiConfig:
    """AI 智能推荐配置。API Key 存 keyring（key='ai_api_key'）。"""

    PROVIDER_DEFAULTS: ClassVar[dict[str, tuple[str, str]]] = {
        "openai": (
            "https://api.openai.com/v1",
            "gpt-4o-mini",
        ),
        "deepseek": (
            "https://api.deepseek.com",
            "deepseek-chat",
        ),
        "qwen": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen-turbo",
        ),
    }

    API_FORMATS: ClassVar[frozenset[str]] = frozenset(
        {"openai_chat", "openai_response", "anthropic"}
    )

    provider: str = (
        "deepseek"  # ponytail: input-only, resolved to base_url/model by __post_init__
    )
    base_url: str = ""
    model: str = ""
    api_format: str = "openai_chat"
    timeout: float = 30.0
    max_chars: int = 300

    def __post_init__(self) -> None:
        if self.provider not in self.PROVIDER_DEFAULTS:
            self.provider = "deepseek"
        if self.api_format not in self.API_FORMATS:
            self.api_format = "openai_chat"
        self._resolve_defaults()

    def _resolve_defaults(self) -> None:
        defaults = self.PROVIDER_DEFAULTS.get(self.provider)
        if defaults:
            if not self.base_url:
                self.base_url = defaults[0]
            if not self.model:
                self.model = defaults[1]
        if self.timeout < 5:
            self.timeout = 5.0
        if self.max_chars < 50:
            self.max_chars = 50


def _default_scripts_enabled() -> bool:
    """ott-script（L3）默认开关：Windows 默认禁用（无 Landlock/Job Object 沙箱）。"""
    return sys.platform != "win32"


@dataclass
class RegistryConfig:
    """开源文库（Registry/OTT）配置。"""

    primary_url: str = ""
    mirror_url: str = ""
    cache_ttl_seconds: int = 3600
    max_content_bytes: int = 1_048_576
    scripts_enabled: bool = field(default_factory=_default_scripts_enabled)

    def __post_init__(self) -> None:
        # 确保 primary_url 是合法字符串，否则视为禁用
        if not isinstance(self.primary_url, str):
            self.primary_url = ""
        self.primary_url = self.primary_url.strip()
        if self.primary_url:
            self.primary_url = self.primary_url.rstrip("/")
            # primary 有值时，mirror 为空才补默认镜像
            if not isinstance(self.mirror_url, str) or not self.mirror_url.strip():
                self.mirror_url = (
                    "https://raw.githubusercontent.com/whynusn/open-typing-texts/main"
                )
            else:
                self.mirror_url = self.mirror_url.strip().rstrip("/")
        else:
            # primary_url 为空 → 整个 registry 禁用，mirror_url 也置空
            self.mirror_url = ""
        if self.cache_ttl_seconds < 0:
            self.cache_ttl_seconds = 3600
        if self.max_content_bytes < 0:
            self.max_content_bytes = 1_048_576
        if not isinstance(self.scripts_enabled, bool):
            self.scripts_enabled = _default_scripts_enabled()


@dataclass
class SourceRepoEntry:
    """单个源仓库订阅条目（OTT Repo 控制面）。"""

    url: str
    enabled: bool = True
    trust_state: str = "unverified"  # verified | unverified | failed
    pinned_pubkey: str = ""
    refresh_ttl_seconds: int = 86400
    etag: str = ""
    added_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            self.url = ""
        else:
            self.url = self.url.strip().rstrip("/")
        if not isinstance(self.enabled, bool):
            self.enabled = True
        if self.trust_state not in {"verified", "unverified", "failed"}:
            self.trust_state = "unverified"
        if not isinstance(self.pinned_pubkey, str):
            self.pinned_pubkey = ""
        if (
            not isinstance(self.refresh_ttl_seconds, int)
            or self.refresh_ttl_seconds <= 0
        ):
            self.refresh_ttl_seconds = 86400
        if not isinstance(self.etag, str):
            self.etag = ""
        if not isinstance(self.added_at, str):
            self.added_at = ""


@dataclass
class SourceReposConfig:
    """多 authority 源仓库订阅列表（OTT Repo 控制面）。

    旧 RegistryConfig.primary_url 在加载时自动迁移为一条等价订阅。
    """

    repos: list[SourceRepoEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.repos, list):
            self.repos = []

    @property
    def enabled_repos(self) -> list[SourceRepoEntry]:
        return [r for r in self.repos if r.enabled and r.url]


@dataclass
class TextSessionConfig:
    """载文会话配置。"""

    small_file_threshold: int = 100_000
    full_shuffle_threshold: int = 1_000_000

    def __post_init__(self) -> None:
        if self.small_file_threshold < 0:
            self.small_file_threshold = 100_000
        if self.full_shuffle_threshold < 0:
            self.full_shuffle_threshold = 1_000_000


@dataclass
class RuntimeConfig:
    """运行时配置，从 JSON 文件加载。"""

    base_url: str = "http://127.0.0.1:8080"
    api_timeout: float = (
        20.0  # 启动期常量：仅 container.py 创建 ApiClient 时使用，运行时不传播变更
    )
    typing_history_max_records: int = 2000  # 打字历史最多保留条数

    text_source_config: TextSourceConfig = field(default_factory=TextSourceConfig)
    wenlai: WenlaiConfig = field(default_factory=WenlaiConfig)
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    source_repos: SourceReposConfig = field(default_factory=SourceReposConfig)
    ai: AiConfig = field(default_factory=AiConfig)
    text_session: TextSessionConfig = field(default_factory=TextSessionConfig)
    catalog_items: list[TextCatalogItem] = field(
        default_factory=list
    )  # ponytail: dynamic server data, never persisted
    ui: dict[str, Any] = field(
        default_factory=dict
    )  # UI 配置（主题/外观等），RinUI 通过桥写入
    _config_path: str | None = field(default=None, repr=False)

    @classmethod
    def load_from_file(cls, config_path: str | None = None) -> "RuntimeConfig":
        if config_path is None:
            config_path = str(user_config_path())

        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                log_error(f"[RuntimeConfig] 配置文件损坏，使用默认配置: {config_path}")
                return cls(_config_path=str(user_config_path()))
            config = cls._from_dict(data)
            config._config_path = config_path
        else:
            config = cls(_config_path=str(user_config_path()))

        # 清理已知的测试/占位订阅（客户端不自动订阅任何远程源，
        # 订阅必须由用户显式添加）
        config._cleanup_stale_subscriptions()
        return config

    def _cleanup_stale_subscriptions(self) -> None:
        """移除已知的测试/占位订阅。"""
        stale = [r for r in self.source_repos.repos if "example.org" in r.url]
        for r in stale:
            self.remove_source_repo(r.url)

    @classmethod
    def ensure_user_config_exists(cls) -> str:
        """Ensure the writable user config exists and return its path.

        Generates from dataclass defaults if the user config does not exist.
        The dataclass is the single source of truth for default values.
        """
        target = user_config_path()
        if target.exists():
            cls._ensure_config_sections(target)
            return str(target)

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as f:
            json.dump(cls()._to_dict(), f, ensure_ascii=False, indent=4)
        return str(target)

    @classmethod
    def _ensure_config_sections(cls, target: Path) -> None:
        """Merge any top-level sections from defaults that the user config lacks.

        Handles corrupted JSON gracefully by regenerating from defaults.
        Uses file lock to prevent concurrent write conflicts.
        """
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log_error(f"[RuntimeConfig] 配置文件损坏，重新生成: {target}")
            data = cls()._to_dict()
            try:
                with target.open("w", encoding="utf-8") as f:
                    try:
                        fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                    except (OSError, AttributeError):
                        pass
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except OSError:
                log_error(f"[RuntimeConfig] 写入配置文件失败：{target}")
            return

        defaults = cls()._to_dict()
        missing = {k: v for k, v in defaults.items() if k not in data}
        if missing:
            data.update(missing)
            try:
                with target.open("w", encoding="utf-8") as f:
                    try:
                        fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                    except (OSError, AttributeError):
                        pass
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except OSError:
                log_error(f"[RuntimeConfig] 合并配置字段失败：{target}")

    @classmethod
    def _from_dict(cls, data: dict) -> "RuntimeConfig":
        base_url = data.get("base_url", "http://127.0.0.1:8080")
        api_timeout = data.get("api_timeout", 20.0)

        sources_data = data.get("text_sources", {})
        sources = {}
        default_key = ""

        for key, source_data in sources_data.items():
            sources[key] = TextSourceEntry.from_dict(
                key=key,
                label=source_data.get("label", key),
                data=source_data,
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

        r_data = data.get("registry", {})
        if not isinstance(r_data, dict):
            r_data = {}
        raw_primary = r_data.get("primary_url")
        raw_mirror = r_data.get("mirror_url")
        registry = RegistryConfig(
            primary_url=cls._safe_str(raw_primary, "", allow_empty=True)
            if isinstance(raw_primary, str)
            else "",
            mirror_url=cls._safe_str(raw_mirror, "", allow_empty=True)
            if isinstance(raw_mirror, str)
            else "",
            cache_ttl_seconds=cls._safe_int(r_data.get("cache_ttl_seconds"), 3600),
            max_content_bytes=cls._safe_int(r_data.get("max_content_bytes"), 1_048_576),
            scripts_enabled=cls._safe_bool(
                r_data.get("scripts_enabled"), _default_scripts_enabled()
            ),
        )

        # 解析 source_repos，并在缺少时从旧 registry.primary_url 自动迁移。
        source_repos = cls._parse_source_repos(data.get("source_repos"))
        if not source_repos.repos and registry.primary_url:
            source_repos = SourceReposConfig(
                repos=[
                    SourceRepoEntry(
                        url=registry.primary_url,
                        enabled=True,
                        trust_state="unverified",
                        refresh_ttl_seconds=registry.cache_ttl_seconds,
                    )
                ]
            )
        if source_repos.repos and registry.primary_url:
            # 仅当 primary_url 不匹配任何订阅（陈旧地址）时才清空；
            # 与订阅一致的 primary_url 保留，作为跨重启"旧 primary"识别依据，
            # 供 update_registry_url 换地址/清空时移除旧订阅（僵尸订阅清理）。
            if not any(r.url == registry.primary_url for r in source_repos.repos):
                registry.primary_url = ""
                registry.mirror_url = ""

        ts_data = data.get("text_session", {})
        if not isinstance(ts_data, dict):
            ts_data = {}
        text_session = TextSessionConfig(
            small_file_threshold=cls._safe_int(
                ts_data.get("small_file_threshold"), 100_000
            ),
            full_shuffle_threshold=cls._safe_int(
                ts_data.get("full_shuffle_threshold"), 1_000_000
            ),
        )

        ai_data = data.get("ai", {})
        if not isinstance(ai_data, dict):
            ai_data = {}
        ai = AiConfig(
            provider=cls._safe_str(ai_data.get("provider"), "deepseek"),
            base_url=cls._safe_str(ai_data.get("base_url"), ""),
            model=cls._safe_str(ai_data.get("model"), ""),
            api_format=cls._safe_str(ai_data.get("api_format"), "openai_chat"),
            timeout=float(cls._safe_int(ai_data.get("timeout"), 30)),
            max_chars=cls._safe_int(ai_data.get("max_chars"), 300),
        )

        ui_data = data.get("ui", {})
        if not isinstance(ui_data, dict):
            ui_data = {}

        return cls(
            base_url=base_url,
            api_timeout=api_timeout,
            typing_history_max_records=cls._safe_int(
                data.get("typing_history_max_records"), 2000
            ),
            text_source_config=text_source_config,
            wenlai=wenlai,
            registry=registry,
            source_repos=source_repos,
            ai=ai,
            text_session=text_session,
            ui=ui_data,
        )

    @classmethod
    def _parse_source_repos(cls, raw: Any) -> SourceReposConfig:
        """从 JSON 解析 source_repos 订阅列表。"""
        if not isinstance(raw, list):
            return SourceReposConfig()
        repos: list[SourceRepoEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            repos.append(
                SourceRepoEntry(
                    url=url,
                    enabled=bool(item.get("enabled", True)),
                    trust_state=cls._safe_str(item.get("trust_state"), "unverified"),
                    pinned_pubkey=cls._safe_str(item.get("pinned_pubkey"), ""),
                    refresh_ttl_seconds=cls._safe_int(
                        item.get("refresh_ttl_seconds"), 86400
                    ),
                    etag=cls._safe_str(item.get("etag"), ""),
                    added_at=cls._safe_str(item.get("added_at"), ""),
                )
            )
        return SourceReposConfig(repos=repos)

    def _ui_get(self, *keys: str, default: Any = "") -> Any:
        """安全读取嵌套 ui 字段，如 config._ui_get("reader_font_path")。"""
        val: Any = self.ui
        for key in keys:
            if not isinstance(val, dict):
                return default
            val = val.get(key, default)
        return val

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

    @staticmethod
    def _safe_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return default
        return str(value).strip().lower() not in ("0", "false", "no", "off")

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

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        self.catalog_items = items

    def update_text_source(self, key: str, label: str, local_path: str) -> None:
        """添加或更新一个本地文本源并持久化到 config.json。"""
        from .text_source_config import Loader, LeaderboardMode, TextSourceEntry

        self.text_source_config.sources[key] = TextSourceEntry(
            key=key,
            label=label,
            loader=Loader.LOCAL_FILE,
            leaderboard_mode=LeaderboardMode.NONE,
            local_path=local_path,
        )
        if not self.text_source_config.default_key:
            self.text_source_config.default_key = key
        self._save_to_file()

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 并持久化到 config.json。"""
        new_base_url = new_base_url.rstrip("/")
        self.base_url = new_base_url
        self._save_to_file()

    def update_registry_url(
        self,
        *,
        primary_url: str | None = None,
        mirror_url: str | None = None,
    ) -> None:
        """更新 Registry 服务地址并持久化到 config.json。

        旧 primary 识别与 bridge.registryPrimaryUrl 显示同源：registry
        字段优先，为空时回退到首个 enabled 订阅（兼容旧代码产出的
        primary_url="" + 订阅在的升级态配置）。仅当显式传入的 primary
        实际变化（old != new）时才同步订阅；同值重应用只持久化字段，
        避免复活用户主动禁用/删除的订阅。仅改镜像（mirror-only）同样
        不触碰订阅。
        - 设置新地址 → 落一条订阅（去重复用），并移除旧 primary 对应订阅
        - 清空地址（设置页语义"留空则禁用"）→ 移除对应订阅，避免僵尸订阅
        - 同值重应用（old == new，如仅改镜像）→ 只持久化，不触碰订阅
        """
        old_primary = self.registry.primary_url
        if not old_primary:
            for repo in self.source_repos.repos:
                if repo.enabled:
                    old_primary = repo.url
                    break
        if primary_url is not None:
            primary_url = primary_url.strip()
            self.registry.primary_url = primary_url.rstrip("/") if primary_url else ""
        if mirror_url is not None:
            self.registry.mirror_url = mirror_url.rstrip("/") if mirror_url else ""
        if primary_url is None:
            # mirror-only：不触碰订阅，仅持久化镜像地址
            self._save_to_file()
            return
        new_primary = self.registry.primary_url
        # 换地址或清空时，移除旧 primary 对应的订阅（僵尸订阅清理）
        if old_primary and old_primary != new_primary:
            self.remove_source_repo(old_primary)
        if new_primary and old_primary != new_primary:
            # 换地址才同步订阅：add_source_repo 内部去重并启用。
            # 同值重应用（old == new，如设置页仅改镜像）不触碰订阅，
            # 否则会复活用户主动禁用的订阅（round-5 P2）。
            self.add_source_repo(new_primary)
        else:
            self._save_to_file()

    def update_scripts_enabled(self, enabled: bool) -> None:
        """更新 ott-script（L3）开关并持久化到 config.json。"""
        self.registry.scripts_enabled = bool(enabled)
        self._save_to_file()

    def add_source_repo(self, url: str, *, added_at: str = "") -> SourceRepoEntry:
        """添加一条源仓库订阅并持久化。"""
        url = url.strip().rstrip("/") if url else ""
        # 去重：同 url 不重复添加，改为启用
        for repo in self.source_repos.repos:
            if repo.url == url:
                repo.enabled = True
                self._save_to_file()
                return repo
        from datetime import datetime, timezone

        entry = SourceRepoEntry(
            url=url,
            enabled=True,
            trust_state="unverified",
            added_at=added_at or datetime.now(timezone.utc).isoformat(),
        )
        self.source_repos.repos.append(entry)
        self._save_to_file()
        return entry

    def remove_source_repo(self, url: str) -> bool:
        """移除一条源仓库订阅并持久化。

        删除的正是 primary_url 对应订阅时同步清空 primary_url，防止
        _from_dict 的旧 primary 自动迁移在下次启动时复活该订阅。
        """
        url = url.strip().rstrip("/") if url else ""
        new_repos = [r for r in self.source_repos.repos if r.url != url]
        if len(new_repos) == len(self.source_repos.repos):
            return False
        self.source_repos.repos = new_repos
        if self.registry.primary_url == url:
            self.registry.primary_url = ""
            self.registry.mirror_url = ""
        self._save_to_file()
        return True

    def set_source_repo_enabled(self, url: str, enabled: bool) -> None:
        """启用/禁用一条源仓库订阅并持久化。"""
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                repo.enabled = enabled
                self._save_to_file()
                return

    def set_source_repo_trust(
        self, url: str, trust_state: str, pinned_pubkey: str = ""
    ) -> None:
        """更新订阅的信任状态并持久化。"""
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                repo.trust_state = trust_state
                if pinned_pubkey:
                    repo.pinned_pubkey = pinned_pubkey
                self._save_to_file()
                return

    def update_source_repo_refresh(
        self, url: str, *, etag: str = "", trust_state: str = ""
    ) -> None:
        """由缓存层更新订阅的 etag 与信任状态。"""
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                if etag:
                    repo.etag = etag
                if trust_state:
                    repo.trust_state = trust_state
                self._save_to_file()
                return

    def _save_to_file(self) -> None:
        """将当前配置持久化到 config.json。

        - 以 _to_dict() 为基写入，确保所有已知字段一致
        - 合并已存在文件中 _to_dict() 不识别的未知字段（前向兼容）
        - 使用文件锁（fcntl.lockf）防止并发写入冲突
        """
        target_path = (
            Path(self._config_path) if self._config_path else user_config_path()
        )
        try:
            new_data = self._to_dict()

            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 文件锁：防止 RinUI AppUIConfigManager 等并发写入冲突。
            # 必须在锁内读取现有文件，否则读取和截断写入之间仍有 lost-update 窗口。
            with target_path.open("a+", encoding="utf-8") as f:
                try:
                    if fcntl is not None:
                        fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                except (OSError, AttributeError):
                    pass  # 非 Unix 平台或锁不可用时降级

                f.seek(0)
                try:
                    existing = json.load(f)
                    if not isinstance(existing, dict):
                        existing = {}
                except (json.JSONDecodeError, OSError):
                    existing = {}

                # 合并已存在文件的未知字段（前向兼容）
                for k, v in existing.items():
                    if k not in new_data:
                        new_data[k] = v

                f.seek(0)
                f.truncate()
                json.dump(new_data, f, ensure_ascii=False, indent=4)
                f.write("\n")
            self._config_path = str(target_path)
        except Exception as e:
            log_error(f"[RuntimeConfig] 持久化配置失败：{e}")

    def reload(self) -> None:
        path = Path(self._config_path) if self._config_path else None
        if path and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            updated = self._from_dict(data)
            self.base_url = updated.base_url
            self.api_timeout = updated.api_timeout
            self.typing_history_max_records = updated.typing_history_max_records
            self.text_source_config = updated.text_source_config
            self.wenlai = updated.wenlai
            self.registry = updated.registry
            self.source_repos = updated.source_repos
            self.ai = updated.ai
            self.text_session = updated.text_session
            self.ui = updated.ui

    def update_ui_config(self, **kwargs: Any) -> None:
        """更新 UI 配置字段并持久化。

        用法: runtime_config.update_ui_config(reader_font_path="/path")
        """
        self.ui.update(kwargs)
        self._save_to_file()

    def _to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "default_text_source_key": self.default_text_source_key,
            "api_timeout": self.api_timeout,
            "typing_history_max_records": self.typing_history_max_records,
            "text_sources": {
                key: {
                    "label": source.label,
                    "loader": source.loader.value,
                    "leaderboard_mode": source.leaderboard_mode.value,
                    **({"local_path": source.local_path} if source.local_path else {}),
                }
                for key, source in self.text_source_config.sources.items()
            },
            "registry": {
                "primary_url": self.registry.primary_url,
                "mirror_url": self.registry.mirror_url,
                "cache_ttl_seconds": self.registry.cache_ttl_seconds,
                "max_content_bytes": self.registry.max_content_bytes,
                "scripts_enabled": self.registry.scripts_enabled,
            },
            "source_repos": [
                {
                    "url": repo.url,
                    "enabled": repo.enabled,
                    "trust_state": repo.trust_state,
                    **(
                        {"pinned_pubkey": repo.pinned_pubkey}
                        if repo.pinned_pubkey
                        else {}
                    ),
                    "refresh_ttl_seconds": repo.refresh_ttl_seconds,
                    **({"etag": repo.etag} if repo.etag else {}),
                    **({"added_at": repo.added_at} if repo.added_at else {}),
                }
                for repo in self.source_repos.repos
            ],
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
            "ai": {
                "provider": self.ai.provider,
                "base_url": self.ai.base_url,
                "model": self.ai.model,
                "api_format": self.ai.api_format,
                "timeout": self.ai.timeout,
                "max_chars": self.ai.max_chars,
            },
            "text_session": {
                "small_file_threshold": self.text_session.small_file_threshold,
                "full_shuffle_threshold": self.text_session.full_shuffle_threshold,
            },
            "ui": self.ui,
        }

    def update_ai_config(
        self,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_format: str | None = None,
        timeout: float | None = None,
        max_chars: int | None = None,
    ) -> None:
        if provider is not None and provider in AiConfig.PROVIDER_DEFAULTS:
            self.ai.provider = provider
            self.ai._resolve_defaults()
        if base_url is not None:
            self.ai.base_url = base_url.rstrip("/")
        if model is not None:
            self.ai.model = model
        if api_format is not None and api_format in AiConfig.API_FORMATS:
            self.ai.api_format = api_format
        if timeout is not None:
            self.ai.timeout = max(timeout, 5.0)
        if max_chars is not None:
            self.ai.max_chars = max(max_chars, 50)
        self._save_to_file()

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

    def update_typing_history_max_records(self, max_records: int) -> None:
        """更新打字历史最大保留条数并持久化。"""
        self.typing_history_max_records = max(100, min(int(max_records), 100000))
        self._save_to_file()
