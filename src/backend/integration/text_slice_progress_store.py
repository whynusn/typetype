"""JSON 文件实现的文本分片进度存储。

以文本内容 SHA-256 hash 为 key，持久化每篇文本的分片进度，
包括：总分段数、当前分段、达标次数、成绩快照、指标设置等。
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TextSliceProgressStore:
    """以文本 hash 为 key 持久化分片进度。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)

    def get_progress(self, text: str) -> dict[str, Any] | None:
        entry = self.load().get(_text_hash(text))
        return entry if isinstance(entry, dict) else None

    def delete_progress(self, text: str) -> None:
        data = self.load()
        key = _text_hash(text)
        if key in data:
            del data[key]
            self.save(data)

    def save_progress(self, text: str, title: str, progress: dict[str, Any]) -> None:
        data = self.load()
        data[_text_hash(text)] = {
            "text_title": title,
            "text_preview": text[:80],
            "last_accessed": progress.get("last_accessed", ""),
            "total_slices": progress.get("total_slices", 0),
            "current_slice": progress.get("current_slice", 0),
            "slice_size": progress.get("slice_size", 0),
            "slice_pass_counts": progress.get("slice_pass_counts", []),
            "slice_stats": progress.get("slice_stats", []),
            "metrics": progress.get("metrics", {}),
            "slice_metrics": progress.get("slice_metrics", []),
            "advance_mode": progress.get("advance_mode", "sequential"),
            "slice_text": progress.get("slice_text", ""),
        }
        self.save(data)
