from dataclasses import dataclass, field
from enum import Enum


class SourceType(Enum):
    """载文项类型。"""

    NETWORK = "network"  # 网络文本源（如极速杯），按 source_key 获取最新文本
    LOCAL_RANKED = "local_ranked"  # 有排行榜的内置文本（如前五百），内容固定，hash 校验
    LOCAL_PRACTICE = "local_practice"  # 无排行榜的本地文本（内置练习/用户上传）


@dataclass
class TextSourceEntry:
    key: str
    label: str
    source_type: SourceType = SourceType.LOCAL_PRACTICE
    local_path: str | None = None
    has_ranking: bool = False  # 仅对 LOCAL_* 有意义；NETWORK 天然支持排行榜

    @staticmethod
    def infer_source_type(local_path: str | None, has_ranking: bool) -> "SourceType":
        """从 config.json 的旧字段推导 source_type。"""
        if not local_path:
            return SourceType.NETWORK
        if has_ranking:
            return SourceType.LOCAL_RANKED
        return SourceType.LOCAL_PRACTICE


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

    def get_source_options(self) -> list[dict[str, str]]:
        return [
            {"key": source.key, "label": source.label}
            for source in self.sources.values()
        ]

    def get_ranking_sources(self) -> list[TextSourceEntry]:
        """返回支持排行榜的来源（NETWORK 天然支持，LOCAL_RANKED 需 hash 校验）。"""
        return [
            s
            for s in self.sources.values()
            if s.source_type in (SourceType.NETWORK, SourceType.LOCAL_RANKED)
        ]
