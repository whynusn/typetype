from typing import Protocol


class LocalTextLoader(Protocol):
    """本地文本读取端口。"""

    def load_text(self, path: str) -> str | None:
        """从给定路径读取文本。"""
