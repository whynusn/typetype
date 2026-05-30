from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TextKind(StrEnum):
    """文本来源类型。"""

    MEMORY_TEXT = "memory_text"
    LOCAL_SOURCE = "local_source"
    LOCAL_ARTICLE = "local_article"
    TRAINER = "trainer"
    REMOTE_TEXT = "remote_text"
    CLIPBOARD = "clipboard"


@dataclass(frozen=True)
class TextHandle:
    kind: TextKind
    identifier: str
    title: str
    char_count: int
    version: str
    source_key: str = ""
    server_text_id: int | None = None


@dataclass(frozen=True)
class SegmentResult:
    content: str
    index: int
    total: int
