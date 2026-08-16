"""动态源刷新策略（快照到期时间计算）。

模式：
- static    永不过期（不调度）
- interval  按 interval_seconds 周期到期（到期自动刷新）
- on_demand 立即过期（仅手动刷新，防无限刷新循环）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MODE_STATIC = "static"
MODE_INTERVAL = "interval"
MODE_ON_DEMAND = "on_demand"

_VALID_MODES = frozenset({MODE_STATIC, MODE_INTERVAL, MODE_ON_DEMAND})


@dataclass
class RefreshPolicy:
    mode: str = MODE_ON_DEMAND
    interval_seconds: int = 0

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            self.mode = MODE_ON_DEMAND
        if not isinstance(self.interval_seconds, int) or self.interval_seconds < 0:
            self.interval_seconds = 0

    def next_refresh_at(self, captured_at: float) -> float | None:
        """static → None（永不过期）；on_demand/interval≤0 → captured_at；否则 captured_at + interval。"""
        if self.mode == MODE_STATIC:
            return None
        if self.interval_seconds > 0:
            return captured_at + self.interval_seconds
        return captured_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            **(
                {"interval_seconds": self.interval_seconds}
                if self.interval_seconds > 0
                else {}
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RefreshPolicy":
        if not isinstance(data, dict):
            return cls()
        raw = data.get("mode", "")
        return cls(
            mode=raw if raw in _VALID_MODES else MODE_ON_DEMAND,
            interval_seconds=data.get("interval_seconds", 0)
            if isinstance(data.get("interval_seconds"), int)
            else 0,
        )


def source_type_of(entry: dict) -> str | None:
    """从 entry 提取源类型（联邦客户端注入的私有字段）。"""
    st = entry.get("_source_type")
    return st if isinstance(st, str) and st else None


def infer_policy(source_type: str | None) -> RefreshPolicy:
    """缺省推断：ott-instance → static；其余（rule/script/bridge）→ on_demand。"""
    if source_type == "ott-instance":
        return RefreshPolicy(MODE_STATIC)
    return RefreshPolicy(MODE_ON_DEMAND)
