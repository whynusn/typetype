"""文本来源配置。

二维正交分解设计（2026-07-04 重构）：

- `Loader`: 数据从哪来 — 决定 TextSourceGateway 路由到哪个 Provider
- `LeaderboardMode`: 成绩怎么处理 — 决定 text_id 决策路径

这两个维度正交，能组合出所有业务场景，避免单一枚举把"加载方式"
和"排行榜行为"耦合在一起导致的循环论证（如旧 LOCAL_RANKED 既表示
"读本地文件"又隐含"回查服务端 text_id"）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Loader(str, Enum):
    """文本数据加载方式 — 决定 TextSourceGateway 路由。"""

    LOCAL_FILE = "local_file"  # 读本地文件（LocalTextLoader / FileSegmentProvider）
    REMOTE_API = "remote_api"  # 调用服务端 API（RemoteTextProvider）
    REGISTRY = "registry"  # 历史 Loader 标识（OttTextProvider）


class LeaderboardMode(str, Enum):
    """排行榜参与方式 — 决定 text_id 解析路径。

    - NONE: 纯练习，不提交成绩
    - SERVER_RESOLVED: 服务端返回 text_id，直接用于提交
    - LOCAL_LOOKUP: 本地内容 hash 回查服务端 text_id（如"前五百"等固定内容）
    """

    NONE = "none"
    SERVER_RESOLVED = "server_resolved"
    LOCAL_LOOKUP = "local_lookup"


@dataclass
class TextSourceEntry:
    """文本来源条目。

    loader 和 leaderboard_mode 正交组合，常见配置：
        本地纯练习:     loader=LOCAL_FILE,  leaderboard_mode=NONE
        本地排行榜文本: loader=LOCAL_FILE,  leaderboard_mode=LOCAL_LOOKUP
        服务端网络源:   loader=REMOTE_API,  leaderboard_mode=SERVER_RESOLVED
        CDN 注册表源:   loader=REGISTRY,    leaderboard_mode=SERVER_RESOLVED
    """

    key: str
    label: str
    loader: Loader = Loader.LOCAL_FILE
    leaderboard_mode: LeaderboardMode = LeaderboardMode.NONE
    local_path: str | None = None

    @property
    def is_local(self) -> bool:
        """是否为本地来源（供 UI 分组使用）。"""
        return self.loader == Loader.LOCAL_FILE

    @classmethod
    def from_dict(cls, key: str, label: str, data: dict) -> "TextSourceEntry":
        """从 config.json 反序列化，自动迁移旧 source_type 字段。"""
        loader = _resolve_loader(data)
        leaderboard_mode = _resolve_leaderboard_mode(data)
        return cls(
            key=key,
            label=label,
            loader=loader,
            leaderboard_mode=leaderboard_mode,
            local_path=data.get("local_path"),
        )


# ---------------------------------------------------------------------------
# 旧 schema 迁移：source_type + has_ranking → loader + leaderboard_mode
# ---------------------------------------------------------------------------

# 旧 SourceType → (Loader, LeaderboardMode) 映射
_LEGACY_SOURCE_TYPE_MAP: dict[str, tuple[Loader, LeaderboardMode]] = {
    "network": (Loader.REMOTE_API, LeaderboardMode.SERVER_RESOLVED),
    "registry": (Loader.REGISTRY, LeaderboardMode.SERVER_RESOLVED),
    "local_ranked": (Loader.LOCAL_FILE, LeaderboardMode.LOCAL_LOOKUP),
    "local_practice": (Loader.LOCAL_FILE, LeaderboardMode.NONE),
}


def _resolve_loader(data: dict) -> Loader:
    """解析 loader，兼容新字段（loader）和旧字段（source_type）。"""
    raw = data.get("loader")
    if raw is None:
        # 新 schema 优先
        raw = data.get("source_type")
    if isinstance(raw, str):
        # 先按新 Loader 枚举值匹配
        try:
            return Loader(raw)
        except ValueError:
            pass
        # 再按旧 source_type 迁移
        if raw in _LEGACY_SOURCE_TYPE_MAP:
            return _LEGACY_SOURCE_TYPE_MAP[raw][0]
    # 无明确 loader 时，按 local_path 兜底推导
    if data.get("local_path"):
        return Loader.LOCAL_FILE
    return Loader.REMOTE_API


def _resolve_leaderboard_mode(data: dict) -> LeaderboardMode:
    """解析 leaderboard_mode，兼容旧 source_type + has_ranking。"""
    raw = data.get("leaderboard_mode")
    if isinstance(raw, str):
        try:
            return LeaderboardMode(raw)
        except ValueError:
            pass
    # 旧 source_type 迁移
    source_type = data.get("source_type")
    if isinstance(source_type, str) and source_type in _LEGACY_SOURCE_TYPE_MAP:
        return _LEGACY_SOURCE_TYPE_MAP[source_type][1]
    # 旧 has_ranking 兜底（仅 local_path 存在时有意义）
    if data.get("has_ranking") is True:
        if data.get("local_path"):
            return LeaderboardMode.LOCAL_LOOKUP
        return LeaderboardMode.SERVER_RESOLVED
    # 无 local_path 的远程源，默认由服务端解析 text_id
    if not data.get("local_path"):
        return LeaderboardMode.SERVER_RESOLVED
    return LeaderboardMode.NONE


@dataclass
class TextSourceConfig:
    sources: dict[str, TextSourceEntry] = field(default_factory=dict)
    default_key: str = ""

    def get_source(self, key: str) -> TextSourceEntry | None:
        return self.sources.get(key)

    def get_default_source(self) -> TextSourceEntry | None:
        if self.default_key:
            return self.sources.get(self.default_key)
        return None

    def get_source_options(self) -> list[dict[str, str | bool]]:
        return [
            {"key": source.key, "label": source.label, "isLocal": source.is_local}
            for source in self.sources.values()
        ]
