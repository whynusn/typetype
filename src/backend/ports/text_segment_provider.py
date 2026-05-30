from __future__ import annotations

from typing import Protocol


class TextSegmentProvider(Protocol):
    """按字符范围提供文本段的端口。"""

    def get_segment(self, start: int, length: int) -> str: ...

    def get_total_chars(self) -> int: ...
