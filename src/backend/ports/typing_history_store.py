"""打字历史记录持久化端口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TypingHistoryStore(ABC):
    """历史记录存储抽象。"""

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """加载全部历史记录数据。"""

    @abstractmethod
    def save(self, data: dict[str, Any]) -> None:
        """保存全部历史记录数据。"""
