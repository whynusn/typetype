from typing import Protocol, runtime_checkable

from ..models.entity.char_stat import CharStat


@runtime_checkable
class CharStatsRepository(Protocol):
    """字符统计持久化协议。

    负责将 CharStat 实体与存储介质（SQLite 等）之间的读写解耦。
    """

    def init_db(self) -> None:
        """初始化数据库（创建表结构）。"""
        ...

    def get(self, char: str) -> CharStat | None:
        """获取单个字符的统计。"""
        ...

    def get_batch(self, chars: list[str]) -> list[CharStat]:
        """批量获取字符统计。"""
        ...

    def get_chars_by_sort(
        self,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
        n: int = 10,
    ) -> list[CharStat]:
        """按指定排序模式获取薄弱字列表。

        Args:
            sort_mode: 排序模式 — "error_rate" | "error_count" | "weighted"
            weights: weighted 模式的权重 {"error_rate": float, "total_count": float, "error_count": float}
            n: 返回数量
        """
        ...

    def get_weakest_chars(self, n: int) -> list[CharStat]:
        """获取最薄弱的 n 个字符统计"""
        ...

    def save(self, stat: CharStat) -> None:
        """保存单个字符的统计（插入或更新）。"""
        ...

    def save_batch(self, stats: list[CharStat]) -> None:
        """批量保存字符统计。"""
        ...

    def get_all(self) -> list[CharStat]:
        """获取全部字符统计。"""
        ...

    def get_all_dirty(self) -> list[CharStat]:
        """获取所有待同步的字符统计（is_dirty=1）。"""
        ...

    def mark_synced(self, chars: list[str], synced_at: str) -> None:
        """标记字符为已同步。"""
        ...
