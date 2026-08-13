"""文本来源配置。

ADR-013 决策 7 收敛后（2026-08-13）：

- `Loader` 收敛为仅 `LOCAL_FILE`，`LeaderboardMode` 枚举整体删除。
  typetype-server 耦合移除后，远程/registry 加载与成绩 text_id 决策
  全部失效，`TextSourceEntry` 简化为 `{key, label, local_path}`。
- 旧的 `source_type` / `has_ranking` legacy 迁移分支随旧 schema 一并删除，
  v1 → v2 配置迁移统一由 `runtime_config._migrate_legacy_v1` 处理。
- QML 契约：`get_source_options()` 返回的 dict 含 `key`/`label`/`isLocal`
  键（`TextLoadPanel.qml` 依赖），v2 下 `isLocal` 恒为 `True`。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextSourceEntry:
    """文本来源条目（v2 schema：仅本地文件来源）。

    v1 的 loader/leaderboard_mode 二维模型已删除；所有条目均为本地文件。
    """

    key: str
    label: str
    local_path: str | None = None

    @property
    def is_local(self) -> bool:
        """是否为本地来源（供 UI 分组使用；v2 下恒为 True）。"""
        return True

    @classmethod
    def from_dict(cls, key: str, label: str, data: dict) -> "TextSourceEntry":
        """从 config.json 反序列化（v2：只读 label/local_path）。"""
        local_path = data.get("local_path")
        return cls(
            key=key,
            label=label,
            local_path=local_path
            if isinstance(local_path, str) and local_path
            else None,
        )


@dataclass
class TextSourceConfig:
    sources: dict[str, TextSourceEntry] = field(default_factory=dict)
    default_key: str = ""

    def get_source(self, key: str) -> TextSourceEntry | None:
        return self.sources.get(key)

    def get_default_source(self) -> TextSourceEntry | None:
        if self.default_key:
            return self.sources.get(self.default_key)
        return None

    def get_source_options(self) -> list[dict[str, str | bool]]:
        return [
            {"key": source.key, "label": source.label, "isLocal": source.is_local}
            for source in self.sources.values()
        ]
