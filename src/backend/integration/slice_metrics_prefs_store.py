"""JSON 文件实现的分片指标偏好存储。

持久化用户最后一次使用的分片指标设置，
使每次载文时自动继承上次的指标配置。
"""

import json
from pathlib import Path
from typing import Any


class SliceMetricsPrefsStore:
    """持久化用户最后一次使用的分片指标设置。"""

    _DEFAULTS = {
        "key_stroke_min": 6.0,
        "speed_min": 100,
        "accuracy_min": 95,
        "pass_count_min": 1,
        "on_fail_action": "retype",
        "auto_decrease_enabled": False,
        "key_stroke_decrease": 0.0,
        "speed_decrease": 0,
        "accuracy_decrease": 0,
    }

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        """加载上次保存的指标偏好。

        Returns:
            包含指标设置的字典。文件不存在或解析失败时返回默认值。
        """
        if not self._path.exists():
            return dict(self._DEFAULTS)
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return dict(self._DEFAULTS)

        if not isinstance(data, dict):
            return dict(self._DEFAULTS)

        # 合并默认值，确保新字段存在
        result = dict(self._DEFAULTS)
        result.update(data)
        return result

    def save(self, prefs: dict[str, Any]) -> None:
        """保存指标偏好到 JSON 文件。

        Args:
            prefs: 包含指标设置的字典。
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)
