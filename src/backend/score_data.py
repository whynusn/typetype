"""
成绩数据结构体

用于封装打字测试的各项指标，底层指标为基础数据，其他指标为计算属性。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from typing_extensions import Dict, List, Union


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

    def to_dict_for_qml(self) -> dict:
        """
        转换为字典格式，用于 QML 传递（保持与前端接口兼容）

        返回:
            dict: 包含成绩数据的字典，格式与原有代码一致
        """
        return {
            "speed": round(self.speed, 2),
            "keyStroke": round(self.keyStroke, 2),
            "codeLength": round(self.codeLength, 2),
            "wrongNum": self.wrong_char_count,
            "charNum": self.char_count,
            "time": round(self.time, 2),
            "date": self.date,
        }

    def get_summary_data(self) -> List[Dict[str, Union[str, float]]]:
        """
        核心数据层：返回原子化的结构数据
        这一步不包含任何 HTML 或格式化字符串，只有纯数据
        """
        return [
            {"label": "速度", "value": self.speed, "unit": "CPM", "format": ".1f"},
            {
                "label": "有效速度",
                "value": self.effectiveSpeed,
                "unit": "CPM",
                "format": ".1f",
            },
            {
                "label": "码长",
                "value": self.codeLength,
                "unit": "击/字",
                "format": ".2f",
            },
            {
                "label": "击键",
                "value": self.keyStroke,
                "unit": "击/秒",
                "format": ".1f",
            },
            {"label": "准确率", "value": self.accuracy, "unit": "%", "format": ".1f"},
        ]

    def get_detailed_summary(self, format_type: str = "plain") -> str:
        """
        视图层：负责将数据渲染为字符串
        """
        data = self.get_summary_data()

        # 根据数据动态生成格式化字符串
        mark = ["", "", "\n"]
        if format_type == "html":
            mark = ["<b>", "</b>", "<br>"]

        formatted_lines = []
        for item in data:
            # 动态格式化数值
            value_str = f"{item['value']:{item['format']}}"
            line = f"{item['label']}: {mark[0]}{value_str}{mark[1]} {item['unit']}{mark[2]}"
            formatted_lines.append(line)

        return "".join(formatted_lines)
