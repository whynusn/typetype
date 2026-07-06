"""JSON 文件实现的打字历史记录存储。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ports.typing_history_store import TypingHistoryStore


class JsonTypingHistoryStore(TypingHistoryStore):
    """历史记录 JSON 文件存储。

    数据结构：
    {
        "version": 1,
        "records": [ { ... }, ... ]
    }
    """

    CURRENT_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._empty()
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(data, dict):
            return self._empty()
        records = data.get("records")
        if not isinstance(records, list):
            return self._empty()
        return {
            "version": self._safe_int(data.get("version"), self.CURRENT_VERSION),
            "records": records,
        }

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.CURRENT_VERSION,
            "records": data.get("records", []),
        }
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)

    def _empty(self) -> dict[str, Any]:
        return {"version": self.CURRENT_VERSION, "records": []}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return default
