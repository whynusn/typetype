"""
会话统计数据结构体

用于封装单次打字会话的各项指标，底层指标为基础数据，其他指标为计算属性。
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class SessionStat:
    """会话统计数据结构体"""

    # 唯一标识
    id: str = field(default_factory=lambda: str(uuid4()))

    # 文本ID（服务端主键，仅服务端文本可提交成绩）
    text_id: str = ""

    # 打字统计数据
    time: float = 0.0
    key_stroke_count: int = 0
    char_count: int = 0
    wrong_char_count: int = 0
    backspace_count: int = 0
    correction_count: int = 0
    date: str = ""

    def __post_init__(self):
        if self.time < 0:
            self.time = 0.0
        if self.key_stroke_count < 0:
            self.key_stroke_count = 0
        if self.char_count < 0:
            self.char_count = 0
        if self.wrong_char_count < 0:
            self.wrong_char_count = 0
        if self.backspace_count < 0:
            self.backspace_count = 0
        if self.correction_count < 0:
            self.correction_count = 0
        if not self.date:
            self.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def speed(self) -> float:
        if self.time == 0:
            return 0.0
        return self.char_count * 60 / self.time

    @property
    def keyStroke(self) -> float:
        if self.time == 0:
            return 0.0
        return self.key_stroke_count / self.time

    @property
    def codeLength(self) -> float:
        if self.char_count == 0:
            return 0.0
        return self.key_stroke_count / self.char_count

    @property
    def accuracy(self) -> float:
        if self.char_count == 0:
            return 100.0
        correct_chars = self.char_count - self.wrong_char_count
        return (correct_chars / self.char_count) * 100

    @property
    def effectiveSpeed(self) -> float:
        return self.speed * (self.accuracy / 100)
