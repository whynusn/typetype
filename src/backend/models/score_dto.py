"""
成绩传输对象（DTO）

用于隔离网络/界面传输结构，避免与领域模型耦合。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..typing.score_data import ScoreData


@dataclass
class ScoreSummaryItemDTO:
    """成绩摘要项 DTO。"""

    label: str
    value: float
    unit: str
    value_format: str


@dataclass
class ScoreSummaryDTO:
    """成绩摘要展示 DTO。"""

    items: list[ScoreSummaryItemDTO]

    @classmethod
    def from_score_data(cls, score_data: "ScoreData") -> "ScoreSummaryDTO":
        """
        从领域对象构建成绩摘要 DTO。

        参数:
            score_data: 成绩领域对象

        返回:
            ScoreSummaryDTO 实例
        """
        return cls(
            items=[
                ScoreSummaryItemDTO(
                    label="速度",
                    value=score_data.speed,
                    unit="字/分",
                    value_format=".1f",
                ),
                ScoreSummaryItemDTO(
                    label="有效速度",
                    value=score_data.effectiveSpeed,
                    unit="字/分",
                    value_format=".1f",
                ),
                ScoreSummaryItemDTO(
                    label="码长",
                    value=score_data.codeLength,
                    unit="击/字",
                    value_format=".2f",
                ),
                ScoreSummaryItemDTO(
                    label="击键",
                    value=score_data.keyStroke,
                    unit="击/秒",
                    value_format=".1f",
                ),
                ScoreSummaryItemDTO(
                    label="准确率",
                    value=score_data.accuracy,
                    unit="%",
                    value_format=".1f",
                ),
            ]
        )

    def to_plain_text(self) -> str:
        """渲染为纯文本格式。"""
        return self._render(value_prefix="", value_suffix="", line_suffix="\n")

    def to_html(self) -> str:
        """渲染为 HTML 格式。"""
        return self._render(value_prefix="<b>", value_suffix="</b>", line_suffix="<br>")

    def _render(self, value_prefix: str, value_suffix: str, line_suffix: str) -> str:
        """按给定标记渲染文本。"""
        lines: list[str] = []
        for item in self.items:
            value_str = f"{item.value:{item.value_format}}"
            lines.append(
                f"{item.label}: {value_prefix}{value_str}{value_suffix} {item.unit}{line_suffix}"
            )
        return "".join(lines)


@dataclass
class HistoryRecordDTO:
    """历史记录传输对象。"""

    speed: float
    key_stroke: float
    code_length: float
    wrong_num: int
    char_num: int
    time: float
    date: str

    @classmethod
    def from_score_data(cls, score_data: "ScoreData") -> "HistoryRecordDTO":
        """
        从领域对象构建历史记录 DTO。

        参数:
            score_data: 成绩领域对象

        返回:
            HistoryRecordDTO 实例
        """
        return cls(
            speed=round(score_data.speed, 2),
            key_stroke=round(score_data.keyStroke, 2),
            code_length=round(score_data.codeLength, 2),
            wrong_num=score_data.wrong_char_count,
            char_num=score_data.char_count,
            time=round(score_data.time, 2),
            date=score_data.date,
        )

    def to_dict(self) -> dict[str, float | int | str]:
        """
        输出与 QML 历史记录兼容的数据结构。

        返回:
            历史记录字典
        """
        return {
            "speed": self.speed,
            "keyStroke": self.key_stroke,
            "codeLength": self.code_length,
            "wrongNum": self.wrong_num,
            "charNum": self.char_num,
            "time": self.time,
            "date": self.date,
        }
