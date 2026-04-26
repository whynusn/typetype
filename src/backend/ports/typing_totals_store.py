from typing import Any, Protocol


class TypingTotalsStore(Protocol):
    """本地打字字数汇总存储端口。"""

    def load(self) -> dict[str, Any]: ...

    def save(self, data: dict[str, Any]) -> None: ...
