"""开源文库视图边界的类型化条目（ADR-016 B2）。

快照条目在 federation / catalog 内部仍是 dict（存储格式即 OTT 条目 +
物化时注入的 ``_repo_*`` / ``_source_*`` 归属字段）；跨到视图层时统一经
``CatalogEntry.from_dict`` 收口——下划线字段的回退规则（``_authority`` →
``authority``、``_source_label`` → ``source_label`` 等）只在这里写一次，
分组模型与后续 Python 侧逻辑不再各自猜字段名。

``raw`` 保留原始 dict：QML 载入路径（loadFederatedEntry 等）仍按原 dict
回传，DTO 不改变对外协议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ON_DEMAND_SOURCE_TYPES = frozenset({"ott-rule", "ott-script", "ott-bridge"})


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


@dataclass(frozen=True)
class RepoRef:
    """条目所属订阅（repo）。"""

    repo_id: str = ""
    name: str = ""
    url: str = ""
    trust_state: str = ""
    max_entries: int = 0


@dataclass(frozen=True)
class CatalogEntry:
    """开源文库列表中的一条快照（视图边界 DTO）。"""

    entry_id: str
    authority: str
    title: str = ""
    source_label: str = ""
    source_type: str = ""
    preview: str = ""
    category: str = ""
    tags: tuple[str, ...] = ()
    char_count: int = 0
    repo: RepoRef = field(default_factory=RepoRef)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def on_demand(self) -> bool:
        """随机源（rule/script/bridge）：组内默认只显示最新一条。"""
        return self.source_type in ON_DEMAND_SOURCE_TYPES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogEntry:
        tags = data.get("tags")
        return cls(
            entry_id=_str(data.get("entry_id")),
            authority=_str(data.get("_authority")) or _str(data.get("authority")),
            title=_str(data.get("title")),
            source_label=_str(data.get("_source_label"))
            or _str(data.get("source_label")),
            source_type=_str(data.get("_source_type")),
            # inline 全文（rule/script/bridge）优先，instance 用 preview 摘要
            preview=_str(data.get("content")) or _str(data.get("preview")),
            category=_str(data.get("category")),
            tags=tuple(t for t in tags if isinstance(t, str))
            if isinstance(tags, list)
            else (),
            char_count=_int(data.get("char_count")) or _int(data.get("charCount")),
            repo=RepoRef(
                repo_id=_str(data.get("_repo_id")),
                name=_str(data.get("_repo_name")),
                url=_str(data.get("_repo_url")),
                trust_state=_str(data.get("_repo_trust_state")),
                max_entries=_int(data.get("_repo_max_entries")),
            ),
            raw=dict(data),
        )

    def matches(self, needle: str) -> bool:
        """搜索命中：标题 / 源名 / 分类 / 标签 / 预览（needle 已小写）。"""
        if not needle:
            return True
        haystack = " ".join(
            (self.title, self.source_label, self.category, " ".join(self.tags))
            + (self.preview,)
        ).lower()
        return needle in haystack
