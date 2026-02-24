"""
成绩数据结构体

用于封装打字测试的各项指标，底层指标为基础数据，其他指标为计算属性。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScoreData:
    """打字成绩数据结构体"""

    # 底层基础指标（直接测量）
    time: float  # 用时 (秒)
    key_stroke_count: int  # 按键次数
    char_count: int  # 输入字符数
    wrong_char_count: int  # 错误字符数

    # 元数据
    date: str  # 日期时间字符串 (YYYY-MM-DD HH:MM:SS)

    # 计算属性（通过 @property 提供）
    # speed: float  # 打字速度 (WPM)
    # keyStroke: float  # 击键频率 (按键数/秒)
    # codeLength: float  # 码长 (按键数/字符数)
    # accuracy: float  # 准确率

    def __post_init__(self):
        """数据初始化后的验证和处理"""
        # 确保用时时长为非负数
        if self.time < 0:
            self.time = 0.0

        # 确保按键次数为非负数
        if self.key_stroke_count < 0:
            self.key_stroke_count = 0

        # 确保字符数为非负数
        if self.char_count < 0:
            self.char_count = 0

        # 确保错误字符数为非负数
        if self.wrong_char_count < 0:
            self.wrong_char_count = 0

        # 如果时间戳为空，使用当前时间
        if not self.date:
            self.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def speed(self) -> float:
        """
        计算打字速度 (Words Per Minute)

        计算: 字符数 * 60 / 用时 = WPM

        返回:
            float: 打字速度 (WPM)
        """
        if self.time == 0:
            return 0.0
        return self.char_count * 60 / self.time

    @property
    def keyStroke(self) -> float:
        """
        计算击键频率 (按键数/秒)

        计算: 按键次数 / 用时

        返回:
            float: 击键频率 (按键数/秒)
        """
        if self.time == 0:
            return 0.0
        return self.key_stroke_count / self.time

    @property
    def codeLength(self) -> float:
        """
        计算码长 (按键数/字符数)

        计算: 按键次数 / 字符数

        返回:
            float: 码长 (按键数/字符数)
        """
        if self.char_count == 0:
            return 0.0
        return self.key_stroke_count / self.char_count

    @property
    def accuracy(self) -> float:
        """
        计算准确率

        计算: (正确字符数 / 总字符数) * 100

        返回:
            float: 准确率百分比 (0-100)
        """
        if self.char_count == 0:
            return 100.0
        correct_chars = self.char_count - self.wrong_char_count
        return (correct_chars / self.char_count) * 100

    @property
    def effectiveSpeed(self) -> float:
        """
        计算有效速度 (考虑准确率的速度)

        计算: speed * (accuracy / 100)

        返回:
            float: 有效速度 (WPM)
        """
        return self.speed * (self.accuracy / 100)
