import json
from pathlib import Path
from typing import Any


class JsonTypingTotalsStore:
    """JSON 文件实现的打字字数汇总存储。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"total_chars": 0, "daily": {}}
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"total_chars": 0, "daily": {}}
        return data if isinstance(data, dict) else {"total_chars": 0, "daily": {}}

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)
