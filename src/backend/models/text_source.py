from dataclasses import dataclass, field


@dataclass
class TextSource:
    """文本来源配置。

    类型说明：
    - local: 本地文本（前五百、中五百等）
    - network_direct: 直接从 URL 获取（如极速杯）
    - network_catalog: 从后端文本库选择（动态获取列表）
    """

    key: str
    label: str
    type: str  # "local" / "network_direct" / "network_catalog"

    # 排行榜相关
    has_ranking: bool = False
    ranking_type: str = ""  # "daily"（每日榜单）/ "permanent"（永久榜单）
    text_id: str = ""  # 文本唯一标识（用于排行榜查询）

    # 本地来源
    local_path: str | None = None

    # 直接网络来源（如极速杯）
    url: str | None = None
    fetcher_key: str | None = None

    # 文本库来源（后端）
    # 不需要配置，通过 API 动态获取


@dataclass
class TextCatalogItem:
    """文本目录项（从后端获取）。"""

    text_id: str  # 文本唯一标识
    label: str  # 显示名称
    description: str = ""  # 描述
    has_ranking: bool = False  # 是否有排行榜
    ranking_type: str = ""  # 排行榜类型


@dataclass
class TextSourceConfig:
    """文本来源配置集合。"""

    sources: dict[str, TextSource] = field(default_factory=dict)
    default_key: str = ""
    catalog_items: list[TextCatalogItem] = field(default_factory=list)

    def get_source(self, key: str) -> TextSource | None:
        """获取指定来源。"""
        return self.sources.get(key)

    def get_default_source(self) -> TextSource | None:
        """获取默认来源。"""
        if self.default_key:
            return self.sources.get(self.default_key)
        return None

    def get_source_options(self) -> list[dict[str, str]]:
        """获取 UI 可选的来源列表（静态配置 + 动态目录）。"""
        options = [{"key": k, "label": v.label} for k, v in self.sources.items()]
        for item in self.catalog_items:
            options.append({"key": item.text_id, "label": item.label})
        return options

    def get_ranking_sources(self) -> list[TextSource]:
        """获取有排行榜的来源列表。"""
        return [s for s in self.sources.values() if s.has_ranking]

    def update_catalog(self, items: list[TextCatalogItem]) -> None:
        """更新文本目录。"""
        self.catalog_items = items
