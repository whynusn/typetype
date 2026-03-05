from typing import Protocol


class TextFetcher(Protocol):
    """文本加载协议，避免在用例层依赖具体服务实现。"""

    def fetch_text(self, url: str) -> str | None: ...
