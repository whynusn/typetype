from typing import Any, Protocol


class ClipboardReader(Protocol):
    """剪贴板读取协议。"""

    def text(self) -> str: ...


class ClipboardWriter(Protocol):
    """剪贴板写入协议。"""

    def setText(self, text: str, /, mode: Any = ...) -> None: ...
