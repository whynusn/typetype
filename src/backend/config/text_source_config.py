from dataclasses import dataclass, field
from enum import Enum


class SourceType(Enum):
    """载文项类型。"""

    NETWORK = "network"  # 网络文本源（如极速杯），按 source_key 获取最新文本
    LOCAL_RANKED = "local_ranked"  # 有排行榜的内置文本（如前五百），内容固定，hash 校验
    LOCAL_PRACTICE = "local_practice"  # 无排行榜的本地文本（内置练习/用户上传）
    REGISTRY = "registry"  # 注册表文本源（外部仓库），通过 RegistryTextProvider 获取


@dataclass
class TextSourceEntry:
    key: str
    label: str
    source_type: SourceType = SourceType.LOCAL_PRACTICE
    local_path: str | None = None
    has_ranking: bool = (
        False  # 对 LOCAL_RANKED/REGISTRY 有意义；NETWORK 天然支持，LOCAL_PRACTICE 忽略
    )

    @staticmethod
    def infer_source_type(local_path: str | None, has_ranking: bool) -> "SourceType":
        """从 config.json 的旧字段推导 source_type。"""
        if not local_path:
            return SourceType.NETWORK
        if has_ranking:
            return SourceType.LOCAL_RANKED
        return SourceType.LOCAL_PRACTICE

    @classmethod
    def from_dict(cls, key: str, label: str, data: dict) -> "TextSourceEntry":
        source_type = (
            SourceType(data["source_type"])
            if "source_type" in data
            else cls.infer_source_type(
                data.get("local_path"), data.get("has_ranking", False)
            )
        )
        return cls(
            key=key,
            label=label,
            source_type=source_type,
            local_path=data.get("local_path"),
            has_ranking=data.get("has_ranking", False),
        )


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
