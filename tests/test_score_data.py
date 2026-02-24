"""
成绩数据结构体测试
"""

import pytest

from src.backend.typing.score_data import ScoreData


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
