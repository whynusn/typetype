"""Score Gateway - DTO 转换 + 剪贴板操作。

将领域对象转换为 DTO，供 UI 层使用。
"""

from ...models.dto.score_dto import HistoryRecordDTO, ScoreSummaryDTO
from ...models.entity.session_stat import SessionStat
from ..ports.clipboard import ClipboardWriter


class ScoreGateway:
    """成绩网关，封装 DTO 转换和剪贴板操作。

    职责：
    - 将 SessionStat 转换为 HistoryRecordDTO
    - 将 SessionStat 转换为 ScoreSummaryDTO
    - 将分数摘要复制到剪贴板

    不负责：
    - 业务流程编排
    - 数据持久化
    """

    def __init__(self, clipboard: ClipboardWriter):
        self._clipboard = clipboard

    def build_history_record(
        self, score_data: SessionStat
    ) -> dict[str, float | int | str]:
        """构建历史记录字典。"""
        return HistoryRecordDTO.from_score_data(score_data).to_dict()

    def build_score_message(self, score_data: SessionStat | None) -> str:
        """构建分数摘要 HTML。"""
        if not score_data:
            return "获取分数失败"
        return ScoreSummaryDTO.from_score_data(score_data).to_html()

    def copy_score_to_clipboard(self, score_data: SessionStat | None) -> None:
        """复制分数摘要纯文本到剪贴板。"""
        if not score_data:
            return
        plain_text = ScoreSummaryDTO.from_score_data(score_data).to_plain_text()
        self._clipboard.setText(plain_text)
