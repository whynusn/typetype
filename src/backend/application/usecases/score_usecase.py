from ...models.dto.score_dto import HistoryRecordDTO, ScoreSummaryDTO
from ...typing.score_data import ScoreData
from ..ports.clipboard import ClipboardWriter


class ScoreUseCase:
    """成绩相关用例，封装 Bridge 外的业务编排。"""

    def __init__(self, clipboard: ClipboardWriter):
        self._clipboard = clipboard

    @staticmethod
    def build_history_record(score_data: ScoreData) -> dict[str, float | int | str]:
        """构建历史记录字典。"""
        return HistoryRecordDTO.from_score_data(score_data).to_dict()

    @staticmethod
    def build_score_message(score_data: ScoreData | None) -> str:
        """构建分数摘要 HTML。"""
        if not score_data:
            return "获取分数失败"
        return ScoreSummaryDTO.from_score_data(score_data).to_html()

    def copy_score_message(self, score_data: ScoreData | None) -> None:
        """复制分数摘要纯文本到剪贴板。"""
        if not score_data:
            return
        plain_text = ScoreSummaryDTO.from_score_data(score_data).to_plain_text()
        self._clipboard.setText(plain_text)
