from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ...models.entity.session_stat import SessionStat


@runtime_checkable
class RankingRepository(Protocol):
    """排行榜协议，用于上传成绩和查询排行榜。"""

    def submit_score(self, session_stat: "SessionStat") -> bool:
        """提交成绩到排行榜。

        Args:
            session_stat: 会话统计数据

        Returns:
            bool: 是否提交成功
        """
        ...

    def get_ranking(
        self, text_source_key: str, text_id: str = "", limit: int = 10
    ) -> list[dict]:
        """获取排行榜。

        Args:
            text_source_key: 文本来源标识
            text_id: 文本唯一标识（永久榜单时使用）
            limit: 返回条数

        Returns:
            list[dict]: 排行榜数据列表
        """
        ...

    def get_my_history(self, limit: int = 20) -> list[dict]:
        """获取我的历史记录。

        Args:
            limit: 返回条数

        Returns:
            list[dict]: 历史记录列表
        """
        ...
