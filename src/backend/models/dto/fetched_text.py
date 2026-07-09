"""获取的文本结果。

用于封装从服务器获取的文本数据，包含 id 和 content。
支持 OTT 多条目格式（entries 数组）。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FetchedText:
    """从服务器获取的文本结果。

    content/title 始终指向最新条目的内容（向后兼容）。
    entries 提供所有历史条目列表（OTT v1+ 格式）。
    """

    content: str
    text_id: int | None = None
    title: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)
    source_key: str = ""
    entry_id: str = ""
    revision_id: str = ""
    content_hash: str = ""
    content_mode: str = "inline"
    segment_count: int = 0
    segment_size_hint: int = 0
