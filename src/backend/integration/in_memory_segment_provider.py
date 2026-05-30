from __future__ import annotations


class InMemorySegmentProvider:
    """基于内存字符串的文本段提供者。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def get_segment(self, start: int, length: int) -> str:
        if start < 0 or length <= 0 or start >= len(self._text):
            return ""
        return self._text[start : start + length]

    def get_total_chars(self) -> int:
        return len(self._text)
