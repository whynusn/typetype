from dataclasses import dataclass


@dataclass
class TextCatalogItem:
    id: int
    source_key: str
    label: str
    description: str = ""
    charCount: int = 0
    has_ranking: bool = False
    category: str = ""       # 来源分类（static / jisubei / daily 等）
    update_freq: str = ""    # 更新频率（static / daily / weekly 等）
