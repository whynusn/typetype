"""
成绩数据结构体测试
"""

import pytest

from src.backend.score_data import ScoreData


class TestScoreDataInitialization:
    """测试 ScoreData 初始化"""

    def test_basic_initialization(self):
        """测试基本初始化"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )
        assert score.time == 60.0
        assert score.key_stroke_count == 300
        assert score.char_count == 240
        assert score.wrong_char_count == 10
        assert score.date == "2024-01-01 00:00:00"

    def test_negative_time_correction(self):
        """测试负时间的自动修正"""
        score = ScoreData(
            time=-10.0,
            key_stroke_count=100,
            char_count=80,
            wrong_char_count=5,
            date="",
        )
        assert score.time == 0.0

    def test_negative_key_stroke_correction(self):
        """测试负按键次数的自动修正"""
        score = ScoreData(
            time=60.0, key_stroke_count=-50, char_count=40, wrong_char_count=2, date=""
        )
        assert score.key_stroke_count == 0

    def test_auto_date_generation(self):
        """测试自动生成时间戳"""
        score = ScoreData(
            time=60.0, key_stroke_count=100, char_count=80, wrong_char_count=5, date=""
        )
        assert score.date
        assert len(score.date) == 19  # YYYY-MM-DD HH:MM:SS


class TestScoreDataCalculations:
    """测试成绩计算属性"""

    def test_speed_calculation(self):
        """测试速度计算"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        # 240 * 60 / 60 = 240
        assert score.speed == 240.0

    def test_speed_zero_time(self):
        """测试时间为零时的速度"""
        score = ScoreData(
            time=0.0, key_stroke_count=100, char_count=80, wrong_char_count=5, date=""
        )
        assert score.speed == 0.0

    def test_keystroke_frequency(self):
        """测试击键频率计算"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        # 300 / 60 = 5
        assert score.keyStroke == 5.0

    def test_keystroke_zero_time(self):
        """测试时间为零时的击键频率"""
        score = ScoreData(
            time=0.0, key_stroke_count=100, char_count=80, wrong_char_count=5, date=""
        )
        assert score.keyStroke == 0.0

    def test_code_length(self):
        """测试码长计算"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        # 300 / 240 = 1.25
        assert score.codeLength == pytest.approx(1.25)

    def test_code_length_zero_chars(self):
        """测试字符数为零时的码长"""
        score = ScoreData(
            time=60.0, key_stroke_count=100, char_count=0, wrong_char_count=0, date=""
        )
        assert score.codeLength == 0.0

    def test_accuracy_perfect(self):
        """测试完美准确率"""
        score = ScoreData(
            time=60.0, key_stroke_count=300, char_count=240, wrong_char_count=0, date=""
        )
        assert score.accuracy == 100.0

    def test_accuracy_with_errors(self):
        """测试有错误时的准确率"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=24,
            date="",
        )
        # (240 - 24) / 240 * 100 = 90
        assert score.accuracy == 90.0

    def test_accuracy_zero_chars(self):
        """测试字符数为零时的准确率"""
        score = ScoreData(
            time=60.0, key_stroke_count=100, char_count=0, wrong_char_count=0, date=""
        )
        assert score.accuracy == 100.0

    def test_effective_speed(self):
        """测试有效速度计算"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=24,
            date="",
        )
        # speed = 240, accuracy = 90%
        # effective_speed = 240 * 0.9 = 216
        assert score.effectiveSpeed == pytest.approx(216.0)


class TestScoreDataOutput:
    """测试数据输出"""

    def test_to_dict_for_qml(self):
        """测试转换为 QML 字典"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        result = score.to_dict_for_qml()

        assert "speed" in result
        assert "keyStroke" in result
        assert "codeLength" in result
        assert "wrongNum" in result
        assert "charNum" in result
        assert "time" in result
        assert "date" in result

        assert result["speed"] == 240.0
        assert result["wrongNum"] == 10
        assert result["charNum"] == 240

    def test_get_summary_data(self):
        """测试获取摘要数据"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        result = score.get_summary_data()

        assert len(result) == 5
        assert result[0]["label"] == "速度"
        assert result[0]["unit"] == "CPM"
        assert result[4]["label"] == "准确率"
        assert result[4]["unit"] == "%"

    def test_get_detailed_summary_plain(self):
        """测试获取详细摘要（纯文本格式）"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        result = score.get_detailed_summary("plain")

        assert "速度:" in result
        assert "CPM" in result
        assert "\n" in result

    def test_get_detailed_summary_html(self):
        """测试获取详细摘要（HTML 格式）"""
        score = ScoreData(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="",
        )
        result = score.get_detailed_summary("html")

        assert "<b>" in result
        assert "</b>" in result
        assert "<br>" in result
