"""
成绩 DTO 测试
"""

from src.backend.models.score_dto import HistoryRecordDTO, ScoreSummaryDTO
from src.backend.typing.score_data import ScoreData


class TestHistoryRecordDTO:
    """测试历史记录 DTO 转换"""

    def test_from_score_data_and_to_dict(self):
        """应可从领域对象转换为 QML 兼容字典"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        dto = HistoryRecordDTO.from_score_data(score)
        result = dto.to_dict()

        assert result == {
            "speed": 240.0,
            "keyStroke": 5.0,
            "codeLength": 1.25,
            "wrongNum": 10,
            "charNum": 240,
            "time": 60.0,
            "date": "2024-01-01 00:00:00",
        }


class TestScoreSummaryDTO:
    """测试成绩摘要 DTO"""

    def test_from_score_data(self):
        """应生成固定顺序的摘要项"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        dto = ScoreSummaryDTO.from_score_data(score)

        assert len(dto.items) == 5
        assert dto.items[0].label == "速度"
        assert dto.items[0].unit == "字/分"
        assert dto.items[4].label == "准确率"
        assert dto.items[4].unit == "%"

    def test_to_plain_text(self):
        """应输出纯文本格式摘要"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        text = ScoreSummaryDTO.from_score_data(score).to_plain_text()

        assert "速度:" in text
        assert "字/分" in text
        assert "\n" in text

    def test_to_html(self):
        """应输出 HTML 格式摘要"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        text = ScoreSummaryDTO.from_score_data(score).to_html()

        assert "<b>" in text
        assert "</b>" in text
        assert "<br>" in text
