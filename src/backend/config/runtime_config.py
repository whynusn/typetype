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
from .app_paths import (
    builtin_ott_repo_url,
    default_ott_hub_url,
    user_config_dir,
    user_config_path,
)
from ..utils.logger import log_error, log_info
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
class OttConfig:
    """OTT 运行时参数（ADR-013 决策 4：由旧 registry 段收纳而来）。

    - cache_ttl_seconds：rule/script 缓存 TTL
    - max_content_bytes：单条目内容上限（federation 传入沙箱）
    - scripts_enabled：L3 ott-script 沙箱开关
    """

    cache_ttl_seconds: int = 3600
    max_content_bytes: int = 1_048_576
    scripts_enabled: bool = field(default_factory=_default_scripts_enabled)

    def __post_init__(self) -> None:
        if self.cache_ttl_seconds < 0:
            self.cache_ttl_seconds = 3600
        if self.max_content_bytes < 0:
            self.max_content_bytes = 1_048_576
        if not isinstance(self.scripts_enabled, bool):
            self.scripts_enabled = _default_scripts_enabled()


@dataclass
class UpdateConfig:
    """OTA 更新检查配置（ADR-014 决策 6）。

    - enabled：是否启用更新检查
    - auto_check：启动后后台自动检查
    - check_interval_hours：自动检查间隔
    - channel：发布通道（stable / beta，预留）
    - mirrors：二进制下载镜像前缀列表（默认空，运行时填默认直链/镜像）
    """

    enabled: bool = True
    auto_check: bool = True
    check_interval_hours: int = 24
    channel: str = "stable"
    mirrors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            self.enabled = True
        if not isinstance(self.auto_check, bool):
            self.auto_check = True
        if (
            not isinstance(self.check_interval_hours, int)
            or self.check_interval_hours <= 0
        ):
            self.check_interval_hours = 24
        if not isinstance(self.channel, str) or self.channel not in {"stable", "beta"}:
            self.channel = "stable"
        if not isinstance(self.mirrors, list):
            self.mirrors = []
        else:
            self.mirrors = [m for m in self.mirrors if isinstance(m, str) and m]


@dataclass
class SourceRepoEntry:
    """单个源仓库订阅条目（OTT Repo 控制面）。"""

    url: str
    enabled: bool = True
    trust_state: str = "unverified"  # verified | pending | unverified | failed
    pinned_pubkey: str = ""
    refresh_ttl_seconds: int = 86400
    etag: str = ""
    added_at: str = ""
    # TUF-lite（ADR-011 Phase 3.6）防回滚链参照：最近一次已接受 manifest 的
    # sha256（canonical JSON）。空串 = 未建立链（首次拉取/旧配置升级）。
    last_snapshot_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            self.url = ""
        else:
            self.url = self.url.strip().rstrip("/")
        if not isinstance(self.enabled, bool):
            self.enabled = True
        if self.trust_state not in {"verified", "pending", "unverified", "failed"}:
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
        if not isinstance(self.last_snapshot_hash, str):
            self.last_snapshot_hash = ""


@dataclass
class SourceReposConfig:
    """多 authority 源仓库订阅列表（OTT Repo 控制面）。"""

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
    """运行时配置，从 JSON 文件加载（schema_version=2，ADR-013 决策 3/4）。"""

    SCHEMA_VERSION: ClassVar[int] = 2

    # v1 顶层特征键：v2 schema 中不存在。用于迁移触发判断——即使配置被
    # 意外 stamp 成 schema_version=2（如 _save_to_file 合并未知字段保留了
    # base_url/registry），只要残留 v1 特征键就补跑迁移（自愈，迁移幂等）。
    V1_LEGACY_KEYS: ClassVar[tuple[str, ...]] = ("base_url", "api_timeout", "registry")

    typing_history_max_records: int = 2000  # 打字历史最多保留条数
    blocked_content_hashes: list[str] = field(default_factory=list)

    text_source_config: TextSourceConfig = field(default_factory=TextSourceConfig)
    wenlai: WenlaiConfig = field(default_factory=WenlaiConfig)
    ott: OttConfig = field(default_factory=OttConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
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
    # ui 字段是否被本实例（RuntimeConfig.update_ui_config）修改过。
    # 不参与序列化/比较：RinUI AppUIConfigManager 运行期直写 config.json 的
    # ui 字段，RuntimeConfig 保存时若本标志为 False 则沿用磁盘值，避免用
    # 启动时快照覆盖运行期主题切换等变更。
    _ui_dirty: bool = field(default=False, repr=False, compare=False)

    @classmethod
    @classmethod
    def _needs_v1_migration(cls, data: Any) -> bool:
        """是否需要对配置执行 v1→v2 迁移。

        - 非 dict / 缺 schema_version / schema_version 非当前版本 → 迁移
        - schema_version 已是 v2 但残留 v1 特征键（base_url/api_timeout/registry）
          → 迁移（自愈：被 _save_to_file 合并未知字段污染的历史配置）
        - 干净 v2 → False（幂等：不再触发）
        """
        if not isinstance(data, dict):
            return True
        if data.get("schema_version") != cls.SCHEMA_VERSION:
            return True
        return any(k in data for k in cls.V1_LEGACY_KEYS)

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
                config = cls(_config_path=config_path)
                config._ensure_builtin_default_repo()
                return config

            if cls._needs_v1_migration(data):
                # v1（缺 schema_version 或残留 v1 特征键）→ 幂等迁移并写回；
                # 已是干净 v2 直接加载。
                raw = data if isinstance(data, dict) else {}
                had_repos = bool(raw.get("source_repos"))
                migrated = cls._migrate_legacy_v1(raw)
                cls._write_migrated(config_path, migrated)
                data = migrated

                config = cls._from_dict(data)
                config._config_path = config_path  # 先绑定路径，后续 save 写入目标文件
                if had_repos and not config.source_repos.repos:
                    # 原有「清空后重新 ensure_builtin」语义：v1 有订阅但迁移
                    # （example.org 占位清理）后全部被移除 → 补默认订阅并持久化，
                    # 避免下次启动读空订阅丢失默认源。
                    config._ensure_builtin_default_repo()
                    config._save_to_file()
                elif "source_repos" not in data:
                    # 全新/极简 v1 配置无 source_repos 键 → 补默认订阅（与 v2 路径一致）
                    config._ensure_builtin_default_repo()
                    config._save_to_file()
                return config

            config = cls._from_dict(data)
            config._config_path = config_path
            # 占位订阅清理：每次加载都执行（不依赖 v1→v2 schema 迁移）。
            # 干净 v2 配置残留的 example.org 占位同样需要清理（2026-08-13 实测：
            # 配置被旧版 _save_to_file 合并未知字段污染后，仅凭 schema_version
            # 判断迁移无法自愈）。清理后若清空全部订阅 → 补默认订阅并持久化。
            if config._cleanup_stale_subscriptions():
                if not config.source_repos.repos:
                    config._ensure_builtin_default_repo()
                config._save_to_file()
            if "source_repos" not in data:
                config._ensure_builtin_default_repo()
            return config

        else:
            config = cls(_config_path=config_path)
            config._ensure_builtin_default_repo()

        return config

    def _cleanup_stale_subscriptions(self) -> bool:
        """移除测试/占位订阅（URL 含 example.org）并持久化。

        每次加载都执行（不依赖 v1→v2 schema 迁移）：干净 v2 配置也可能
        残留 example.org 占位（如历史版本 _save_to_file 合并未知字段写入，
        2026-08-13 实测）。返回是否发生了清理。
        """
        stale = [r for r in self.source_repos.repos if "example.org" in r.url]
        if not stale:
            return False
        for r in stale:
            self.remove_source_repo(r.url)
        return True

    @classmethod
    def _migrate_legacy_v1(cls, raw_data: dict) -> dict:
        """v1 → v2 幂等迁移（纯函数，不写盘）。

        只处理旧 v1 结构（ADR-013 决策 3/4/6，Phase 0）：
        - 删除 `base_url`、`api_timeout`
        - 删除 `registry.primary_url` / `registry.mirror_url`
        - `registry.{cache_ttl_seconds, max_content_bytes, scripts_enabled}`
          保值迁移到新顶级段 `ott`
        - `text_sources`：丢弃 server/registry 条目与
          `loader`/`leaderboard_mode`/`source_type`/`has_ranking` 键；
          本地条目重写为 `{label, local_path}`
        - `font_config.json` 折叠进 `ui.reader_font_path`（文件保留不删）
        - 移除 URL 含 `example.org` 的 `source_repos` 占位订阅
        - stamp `"schema_version": 2`
        """
        data = dict(raw_data)

        # 删除 server 耦合字段
        data.pop("base_url", None)
        data.pop("api_timeout", None)

        # registry 段：primary_url/mirror_url 删除，运行时参数收纳到新顶级段 ott
        registry = data.get("registry")
        if isinstance(registry, dict):
            ott: dict[str, Any] = {}
            if registry.get("cache_ttl_seconds") is not None:
                ott["cache_ttl_seconds"] = cls._safe_int(
                    registry.get("cache_ttl_seconds"), 3600
                )
            if registry.get("max_content_bytes") is not None:
                ott["max_content_bytes"] = cls._safe_int(
                    registry.get("max_content_bytes"), 1_048_576
                )
            if registry.get("scripts_enabled") is not None:
                ott["scripts_enabled"] = cls._safe_bool(
                    registry.get("scripts_enabled"), _default_scripts_enabled()
                )
            if ott:
                data["ott"] = ott
        data.pop("registry", None)

        # text_sources：丢弃 server/registry 条目与 legacy 字段，
        # 本地条目重写为 {label, local_path}（保留 local_path）
        sources = data.get("text_sources")
        if isinstance(sources, dict):
            rewritten: dict[str, Any] = {}
            for key, source in sources.items():
                if not isinstance(source, dict):
                    continue
                loader = source.get("loader")
                source_type = source.get("source_type")
                if loader in ("remote_api", "registry") or source_type in (
                    "network",
                    "registry",
                ):
                    continue  # server/registry 条目整体丢弃
                local_path = source.get("local_path")
                if not isinstance(local_path, str) or not local_path:
                    continue  # v2 仅本地文件来源，无路径条目无意义
                rewritten[key] = {
                    "label": source.get("label", key),
                    "local_path": local_path,
                }
            if rewritten:
                data["text_sources"] = rewritten
            else:
                data.pop("text_sources", None)

        # font_config.json 折叠（仅当 ui.reader_font_path 为空；文件保留不删）
        cls._merge_font_config(data)

        # example.org 占位订阅清理（原 _cleanup_stale_subscriptions 逻辑并入迁移）
        source_repos = data.get("source_repos")
        if isinstance(source_repos, list):
            kept = [
                r
                for r in source_repos
                if isinstance(r, dict)
                and isinstance(r.get("url"), str)
                and "example.org" not in r["url"]
            ]
            data["source_repos"] = kept

        # stamp
        data["schema_version"] = cls.SCHEMA_VERSION
        return data

    @classmethod
    def _merge_font_config(cls, data: dict) -> None:
        """font_config.json 折叠：reader_font_path 合并进 ui.reader_font_path。

        仅当 `~/.config/typetype/font_config.json`（跨平台用 user_config_dir()）
        存在且 `ui.reader_font_path` 为空时生效；font_config.json 本身保留不动。
        """
        try:
            font_cfg_path = user_config_dir() / "font_config.json"
            if not font_cfg_path.exists():
                return
            font_cfg = json.loads(font_cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        reader_font_path = font_cfg.get("reader_font_path")
        if not isinstance(reader_font_path, str) or not reader_font_path:
            return
        ui = data.get("ui")
        if not isinstance(ui, dict):
            ui = {}
        if ui.get("reader_font_path"):
            return  # ui.reader_font_path 已存在，不覆盖
        ui["reader_font_path"] = reader_font_path
        data["ui"] = ui

    @staticmethod
    def _write_migrated(config_path: str, data: dict) -> None:
        """迁移后的 v2 配置写回磁盘（文件锁 + 原子写，复用 _save_to_file 思路）。"""
        target_path = Path(config_path)
        tmp_path = target_path.with_name(target_path.name + ".tmp")
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("a+", encoding="utf-8") as f:
                try:
                    if fcntl is not None:
                        fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                except (OSError, AttributeError):
                    pass  # 非 Unix 平台或锁不可用时降级
                with tmp_path.open("w", encoding="utf-8") as tmp:
                    json.dump(data, tmp, ensure_ascii=False, indent=4)
                    tmp.write("\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                f.close()
                os.replace(tmp_path, target_path)
        except Exception as e:
            log_error(f"[RuntimeConfig] 迁移后写回配置失败：{e}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def _ensure_builtin_default_repo(self) -> None:
        if self.source_repos.repos:
            return
        self.source_repos.repos.append(
            SourceRepoEntry(url=builtin_ott_repo_url(), enabled=True)
        )
        # 默认订阅 hub（开箱即用）；离线兜底仍由 builtin 提供
        self.source_repos.repos.append(
            SourceRepoEntry(url=default_ott_hub_url(), enabled=True)
        )

    @classmethod
    def _fresh_with_builtin(cls) -> "RuntimeConfig":
        config = cls()
        config._ensure_builtin_default_repo()
        return config

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
            json.dump(
                cls._fresh_with_builtin()._to_dict(), f, ensure_ascii=False, indent=4
            )
        return str(target)

    @classmethod
    def _ensure_config_sections(cls, target: Path) -> None:
        """Merge any top-level sections from defaults that the user config lacks.

        v1（缺 schema_version）配置先跑幂等迁移，再合并缺省段，保证
        schema_version 的 stamp 只由迁移逻辑产生。Handles corrupted JSON
        gracefully by regenerating from defaults. Uses file lock to prevent
        concurrent write conflicts.
        """
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log_error(f"[RuntimeConfig] 配置文件损坏，重新生成: {target}")
            data = cls._fresh_with_builtin()._to_dict()
            try:
                with target.open("w", encoding="utf-8") as f:
                    try:
                        if fcntl is not None:
                            fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                    except (OSError, AttributeError):
                        pass
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except OSError:
                log_error(f"[RuntimeConfig] 写入配置文件失败：{target}")
            return

        if cls._needs_v1_migration(data):
            data = cls._migrate_legacy_v1(data if isinstance(data, dict) else {})

        defaults = cls._fresh_with_builtin()._to_dict()
        missing = {k: v for k, v in defaults.items() if k not in data}
        if missing:
            data.update(missing)
            try:
                with target.open("w", encoding="utf-8") as f:
                    try:
                        if fcntl is not None:
                            fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                    except (OSError, AttributeError):
                        pass
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except OSError:
                log_error(f"[RuntimeConfig] 合并配置字段失败：{target}")

    @classmethod
    def _from_dict(cls, data: dict) -> "RuntimeConfig":
        sources_data = data.get("text_sources", {})
        if not isinstance(sources_data, dict):
            sources_data = {}
        sources = {}
        default_key = ""

        for key, source_data in sources_data.items():
            if not isinstance(source_data, dict):
                continue
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

        ott_data = data.get("ott", {})
        if not isinstance(ott_data, dict):
            ott_data = {}
        ott = OttConfig(
            cache_ttl_seconds=cls._safe_int(ott_data.get("cache_ttl_seconds"), 3600),
            max_content_bytes=cls._safe_int(
                ott_data.get("max_content_bytes"), 1_048_576
            ),
            scripts_enabled=cls._safe_bool(
                ott_data.get("scripts_enabled"), _default_scripts_enabled()
            ),
        )

        update_data = data.get("update", {})
        if not isinstance(update_data, dict):
            update_data = {}
        raw_mirrors = update_data.get("mirrors")
        update = UpdateConfig(
            enabled=cls._safe_bool(update_data.get("enabled"), True),
            auto_check=cls._safe_bool(update_data.get("auto_check"), True),
            check_interval_hours=cls._safe_int(
                update_data.get("check_interval_hours"), 24
            ),
            channel=cls._safe_str(update_data.get("channel"), "stable"),
            mirrors=[m for m in raw_mirrors if isinstance(m, str) and m]
            if isinstance(raw_mirrors, list)
            else [],
        )

        # 解析 source_repos（v2：纯订阅列表，无 primary_url 迁移）
        source_repos = cls._parse_source_repos(data.get("source_repos"))

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
            timeout=cls._safe_float(ai_data.get("timeout"), 30.0),
            max_chars=cls._safe_int(ai_data.get("max_chars"), 300),
        )

        ui_data = data.get("ui", {})
        if not isinstance(ui_data, dict):
            ui_data = {}

        raw_blocked = data.get("blocked_content_hashes")
        blocked_content_hashes = (
            [h for h in raw_blocked if isinstance(h, str) and h]
            if isinstance(raw_blocked, list)
            else []
        )
        return cls(
            typing_history_max_records=cls._safe_int(
                data.get("typing_history_max_records"), 2000
            ),
            blocked_content_hashes=blocked_content_hashes,
            text_source_config=text_source_config,
            wenlai=wenlai,
            ott=ott,
            update=update,
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
                    enabled=cls._safe_bool(item.get("enabled"), True),
                    trust_state=cls._safe_str(item.get("trust_state"), "unverified"),
                    pinned_pubkey=cls._safe_str(item.get("pinned_pubkey"), ""),
                    refresh_ttl_seconds=cls._safe_int(
                        item.get("refresh_ttl_seconds"), 86400
                    ),
                    etag=cls._safe_str(item.get("etag"), ""),
                    added_at=cls._safe_str(item.get("added_at"), ""),
                    last_snapshot_hash=cls._safe_str(
                        item.get("last_snapshot_hash"), ""
                    ),
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
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "1", "yes"):
                return True
            if v in ("false", "0", "no", ""):
                return False
            return default
        if isinstance(value, (int, float)):
            return value != 0
        return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """JSON → float 安全转换。

        直接 int() 会截断浮点（如 30.5 → 30），本方法保留精度；
        非数字类型/非法字符串回退 default。
        """
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @property
    def default_text_source_key(self) -> str:
        return self.text_source_config.default_key

    def get_text_source(self, key: str | None = None) -> TextSourceEntry | None:
        k = key or self.default_text_source_key
        return self.text_source_config.get_source(k)

    def get_text_source_options(self) -> list[dict[str, str | bool]]:
        options = self.text_source_config.get_source_options()
        options.extend(
            {"key": item.source_key, "label": item.label} for item in self.catalog_items
        )
        return options

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        self.catalog_items = items

    def update_text_source(self, key: str, label: str, local_path: str) -> None:
        """添加或更新一个本地文本源并持久化到 config.json（v2：{label, local_path}）。"""
        from .text_source_config import TextSourceEntry

        self.text_source_config.sources[key] = TextSourceEntry(
            key=key,
            label=label,
            local_path=local_path,
        )
        if not self.text_source_config.default_key:
            self.text_source_config.default_key = key
        self._save_to_file()

    def update_registry_url(
        self,
        *,
        primary_url: str | None = None,
        mirror_url: str | None = None,
    ) -> None:
        """更新 Registry 主地址订阅并持久化（v2 纯订阅化，ADR-013 决策 5）。

        v2 起 `registry.primary_url`/`mirror_url` 字段已删除，本方法只维护
        `source_repos` 订阅：
        - 显式传入 primary_url（新地址）→ 去重落一条订阅，并移除旧主订阅
        - primary_url 为空串（设置页语义"留空则禁用"）→ 移除当前主订阅
        - 目标地址已存在订阅（含被禁用）→ 同值重应用，不复活/不删除
        - 仅传 mirror_url（mirror-only）→ v2 无 mirror 概念，仅持久化不触碰订阅
        """
        if primary_url is None:
            # mirror-only：无订阅动作，仅持久化（兼容旧调用方）
            self._save_to_file()
            return

        old_primary = ""
        for repo in self.source_repos.repos:
            if repo.enabled and not repo.url.startswith("file://"):
                old_primary = repo.url
                break

        new_primary = primary_url.strip().rstrip("/") if primary_url else ""

        # 同值重应用：目标地址已存在订阅（无论启用与否）→ 仅持久化，不触碰
        # 订阅，避免复活用户主动禁用/删除的订阅。
        if any(r.url == new_primary for r in self.source_repos.repos):
            self._save_to_file()
            return

        # 清空地址 → 移除当前主订阅（僵尸订阅清理）
        if not new_primary:
            if old_primary:
                self.remove_source_repo(old_primary)
            else:
                self._save_to_file()
            return

        # 换地址 → 移除旧主订阅，去重落新订阅（add_source_repo 内部去重并启用）
        if old_primary and old_primary != new_primary:
            self.remove_source_repo(old_primary)
        self.add_source_repo(new_primary)

    def update_scripts_enabled(self, enabled: bool) -> None:
        """更新 ott-script（L3）开关并持久化到 config.json（ott 段）。"""
        self.ott.scripts_enabled = bool(enabled)
        self._save_to_file()

    def add_blocked_content_hash(self, content_hash: str) -> None:
        """加入本地内容屏蔽清单（takedown 生效）并持久化。"""
        cleaned = content_hash.strip()
        if cleaned and cleaned not in self.blocked_content_hashes:
            self.blocked_content_hashes.append(cleaned)
            self._save_to_file()

    def remove_blocked_content_hash(self, content_hash: str) -> bool:
        """从本地内容屏蔽清单移除；存在才持久化并返回 True。"""
        cleaned = content_hash.strip()
        remaining = [h for h in self.blocked_content_hashes if h != cleaned]
        if len(remaining) == len(self.blocked_content_hashes):
            return False
        self.blocked_content_hashes = remaining
        self._save_to_file()
        return True

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
        """移除一条源仓库订阅并持久化。"""
        url = url.strip().rstrip("/") if url else ""
        new_repos = [r for r in self.source_repos.repos if r.url != url]
        if len(new_repos) == len(self.source_repos.repos):
            return False
        self.source_repos.repos = new_repos
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

    def confirm_source_repo_trust(self, url: str) -> None:
        """用户显式确认信任订阅（TOFU pending → verified）。

        保留已固定的公钥；无固定公钥的订阅不改变状态（confirm 仅针对
        pending 且有 pinned_pubkey 的条目生效）。
        """
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                if repo.trust_state == "pending" and repo.pinned_pubkey:
                    repo.trust_state = "verified"
                    self._save_to_file()
                    log_info(f"[RuntimeConfig] 用户确认信任订阅: {url}")
                return

    def reject_source_repo_trust(self, url: str) -> None:
        """用户显式拒绝信任订阅（pending → unverified，清空固定公钥）。

        不删除订阅：清空 pinned_pubkey 后，下次刷新会重新评估并再次
        进入 pending，等待用户重新决策。
        """
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                if repo.trust_state == "pending":
                    repo.trust_state = "unverified"
                    repo.pinned_pubkey = ""
                    self._save_to_file()
                    log_info(f"[RuntimeConfig] 用户拒绝信任订阅: {url}")
                return

    def update_source_repo_refresh(
        self,
        url: str,
        *,
        etag: str = "",
        trust_state: str = "",
        last_snapshot_hash: str = "",
    ) -> None:
        """由缓存层更新订阅的 etag / 信任状态 / TUF-lite 快照参照。"""
        url = url.strip().rstrip("/") if url else ""
        for repo in self.source_repos.repos:
            if repo.url == url:
                if etag:
                    repo.etag = etag
                if trust_state:
                    repo.trust_state = trust_state
                if last_snapshot_hash:
                    repo.last_snapshot_hash = last_snapshot_hash
                self._save_to_file()
                return

    def _save_to_file(self) -> None:
        """将当前配置持久化到 config.json。

        - 以 _to_dict() 为基写入，确保所有已知字段一致
        - 合并已存在文件中 _to_dict() 不识别的未知字段（前向兼容）
        - 使用文件锁（fcntl.lockf）保护"读-合并-写"临界区
        - 原子写：先写同目录临时文件（flush + fsync），再 os.replace
          原子替换，崩溃/序列化异常不会损坏原 config.json
        - ui 字段冲突处理：见 _ui_dirty 注释
        """
        target_path = (
            Path(self._config_path) if self._config_path else user_config_path()
        )
        tmp_path = target_path.with_name(target_path.name + ".tmp")
        try:
            new_data = self._to_dict()

            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 文件锁：防止 RinUI AppUIConfigManager 等并发写入冲突。
            # 必须在锁内读取现有文件，否则读取和替换之间仍有 lost-update 窗口。
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

                # ui 字段冲突修复：本实例未通过 update_ui_config 修改过 ui
                # （_ui_dirty=False）时，沿用磁盘上现有 ui 值，避免用启动时
                # 快照覆盖 AppUIConfigManager 运行期直写的主题切换等变更；
                # 磁盘无 ui 键时回退 self.ui。_ui_dirty=True 时用 self.ui
                # 并重置标志（本次保存已消费该修改）。
                if not self._ui_dirty:
                    if "ui" in existing:
                        new_data["ui"] = existing["ui"]
                else:
                    self._ui_dirty = False

                # 原子写：临时文件 + os.replace。os.replace 必须在持锁范围内
                # 执行（否则释放锁到 replace 之间存在 lost-update 竞态窗口），
                # 但 Windows 不允许替换仍被打开的文件——因此先关闭 f 句柄
                # 再 replace（with 块退出时重复 close 是幂等的）。
                with tmp_path.open("w", encoding="utf-8") as tmp:
                    json.dump(new_data, tmp, ensure_ascii=False, indent=4)
                    tmp.write("\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())

                f.close()
                os.replace(tmp_path, target_path)
                self._config_path = str(target_path)
        except Exception as e:
            log_error(f"[RuntimeConfig] 持久化配置失败：{e}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def reload(self) -> None:
        path = Path(self._config_path) if self._config_path else None
        if path and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            updated = self._from_dict(data)
            self.typing_history_max_records = updated.typing_history_max_records
            self.blocked_content_hashes = updated.blocked_content_hashes
            self.text_source_config = updated.text_source_config
            self.wenlai = updated.wenlai
            self.ott = updated.ott
            self.update = updated.update
            self.source_repos = updated.source_repos
            self.ai = updated.ai
            self.text_session = updated.text_session
            self.ui = updated.ui

    def update_ui_config(self, **kwargs: Any) -> None:
        """更新 UI 配置字段并持久化。

        用法: runtime_config.update_ui_config(reader_font_path="/path")
        """
        self.ui.update(kwargs)
        self._ui_dirty = True
        self._save_to_file()

    def _to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "default_text_source_key": self.default_text_source_key,
            "typing_history_max_records": self.typing_history_max_records,
            "blocked_content_hashes": list(self.blocked_content_hashes),
            "text_sources": {
                key: {
                    "label": source.label,
                    **({"local_path": source.local_path} if source.local_path else {}),
                }
                for key, source in self.text_source_config.sources.items()
            },
            "ott": {
                "cache_ttl_seconds": self.ott.cache_ttl_seconds,
                "max_content_bytes": self.ott.max_content_bytes,
                "scripts_enabled": self.ott.scripts_enabled,
            },
            "update": {
                "enabled": self.update.enabled,
                "auto_check": self.update.auto_check,
                "check_interval_hours": self.update.check_interval_hours,
                "channel": self.update.channel,
                "mirrors": list(self.update.mirrors),
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
                    **(
                        {"last_snapshot_hash": repo.last_snapshot_hash}
                        if repo.last_snapshot_hash
                        else {}
                    ),
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
