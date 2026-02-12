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

    @classmethod
    def from_text_properties_data(cls, data: dict) -> "ScoreData":
        """
        从 text_properties.py 的 _get_new_record 方法返回的字典创建 ScoreData 实例

        参数:
            data: 包含成绩数据的字典

        返回:
            ScoreData: 成绩数据结构体实例
        """
        # 计算底层指标
        total_chars = int(data.get("charNum", 0))
        wrong_chars = int(data.get("wrongNum", 0))
        key_stroke = int(
            data.get("keyStroke", 0) * data.get("time", 1)
        )  # 从频率计算次数
        time_sec = float(data.get("time", 0))

        return cls(
            time=time_sec,
            key_stroke_count=key_stroke,
            char_count=total_chars,
            wrong_char_count=wrong_chars,
            date=str(data.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
        )

    def to_dict_for_qml(self) -> dict:
        """
        转换为字典格式，用于 QML 传递（保持与原有接口兼容）

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

    def is_better_than(self, other: "ScoreData", metric: str = "speed") -> bool:
        """
        与另一个成绩比较

        参数:
            other: 另一个成绩数据
            metric: 比较指标 ('speed', 'accuracy', 'effectiveSpeed', 'efficiency')

        返回:
            bool: 如果当前成绩更好则返回 True
        """
        if metric == "speed":
            return self.speed > other.speed
        elif metric == "accuracy":
            return self.accuracy > other.accuracy
        elif metric == "effectiveSpeed":
            return self.effectiveSpeed > other.effectiveSpeed
        elif metric == "efficiency":
            # 效率 = 有效速度 / 错误数（错误数为0时返回有效速度）
            eff_self = (
                self.effectiveSpeed
                if self.wrong_char_count == 0
                else self.effectiveSpeed / (self.wrong_char_count + 1)
            )
            eff_other = (
                other.effectiveSpeed
                if other.wrong_char_count == 0
                else other.effectiveSpeed / (other.wrong_char_count + 1)
            )
            return eff_self > eff_other
        else:
            raise ValueError(f"不支持的比较指标: {metric}")

    @classmethod
    def get_best_score(
        cls, scores: list["ScoreData"], metric: str = "speed"
    ) -> Optional["ScoreData"]:
        """
        从成绩列表中获取最佳成绩

        参数:
            scores: 成绩列表
            metric: 最佳指标 ('speed', 'accuracy', 'effectiveSpeed', 'efficiency')

        返回:
            Optional[ScoreData]: 最佳成绩，列表为空时返回 None
        """
        if not scores:
            return None

        if metric == "speed":
            return max(scores, key=lambda s: s.speed)
        elif metric == "accuracy":
            return max(scores, key=lambda s: s.accuracy)
        elif metric == "effectiveSpeed":
            return max(scores, key=lambda s: s.effectiveSpeed)
        elif metric == "efficiency":
            return max(
                scores,
                key=lambda s: (
                    s.effectiveSpeed
                    if s.wrong_char_count == 0
                    else s.effectiveSpeed / (s.wrong_char_count + 1)
                ),
            )
        else:
            raise ValueError(f"不支持的指标: {metric}")
