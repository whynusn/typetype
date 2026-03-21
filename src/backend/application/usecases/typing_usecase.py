"""Typing Use Case - 打字统计业务流程编排。

协调 TypingService 和 ScoreGateway，完成打字统计的完整流程。
"""

from ...models.entity.session_stat import SessionStat
from ..gateways.score_gateway import ScoreGateway


class TypingUseCase:
    """打字统计用例，编排打字流程。

    职责：
    - 构建历史记录（调用 ScoreGateway）
    - 构建分数摘要（调用 ScoreGateway）
    - 复制分数到剪贴板（调用 ScoreGateway）

    不负责：
    - 打字统计逻辑（由 TypingService 负责）
    - 状态管理（由 TypingService 负责）
    - UI 信号发射（由 Bridge 负责）
    """

    def __init__(self, score_gateway: ScoreGateway):
        self._score_gateway = score_gateway

    def build_history_record(
        self, score_data: SessionStat
    ) -> dict[str, float | int | str]:
        """构建历史记录字典。"""
        return self._score_gateway.build_history_record(score_data)

    def build_score_message(self, score_data: SessionStat | None) -> str:
        """构建分数摘要 HTML。"""
        return self._score_gateway.build_score_message(score_data)

    def copy_score_to_clipboard(self, score_data: SessionStat | None) -> None:
        """复制分数摘要到剪贴板。"""
        self._score_gateway.copy_score_to_clipboard(score_data)
