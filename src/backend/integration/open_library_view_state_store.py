"""开源文库视图状态（组展开/收起）的 JSON 持久化。

只记录用户**显式**切换过的组（authority → bool）；没记录的组走智能默认
（见 OpenLibraryListModel.default_expanded）。文件损坏或不存在时视为空。
"""

from __future__ import annotations

import json
from pathlib import Path

_MAX_KEYS = 500  # 防止长期使用后无界增长（删掉的源不会自动清理）


class OpenLibraryViewStateStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load_expanded(self) -> dict[str, bool]:
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        raw = data.get("expanded") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return {}
        return {
            k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, bool)
        }

    def save_expanded(self, expanded: dict[str, bool]) -> None:
        items = list(expanded.items())[-_MAX_KEYS:]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump({"expanded": dict(items)}, f, ensure_ascii=False, indent=2)
        tmp.replace(self._path)
