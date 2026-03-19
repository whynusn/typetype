from dataclasses import dataclass
from datetime import datetime


@dataclass
class CharStat:
    """单字打字统计实体。

    记录每个字符的输入历史，用于跨会话累积统计。
    聚合数据天然无冲突 —— 每个字只有一个维度的值，
    不存在"本地说 100 次、远端说 200 次"的矛盾。
    """

    char: str
    char_count: int = 0
    error_char_count: int = 0
    total_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    last_seen: str = ""

    def __post_init__(self):
        if not self.char:
            raise ValueError("char cannot be empty")
        if len(self.char) != 1:
            raise ValueError("char must be exactly one character")
        if self.char_count < 0:
            self.char_count = 0
        if self.error_char_count < 0:
            self.error_char_count = 0
        if self.total_ms < 0:
            self.total_ms = 0.0

    def accumulate(self, keystroke_ms: float, is_error: bool) -> None:
        """累积一次字符上屏结果。

        @param keystroke_ms: 此次字符的按键耗时（毫秒）
        @param is_error: 是否错误字符
        """
        self.char_count += 1
        self.total_ms += keystroke_ms

        if is_error:
            self.error_char_count += 1

        if self.min_ms == 0.0 or keystroke_ms < self.min_ms:
            self.min_ms = keystroke_ms

        if keystroke_ms > self.max_ms:
            self.max_ms = keystroke_ms

        self.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def avg_ms(self) -> float:
        if self.char_count == 0:
            return 0.0
        return self.total_ms / self.char_count

    @property
    def error_rate(self) -> float:
        if self.char_count == 0:
            return 0.0
        return (self.error_char_count / self.char_count) * 100

    def merge(self, other: "CharStat") -> None:
        """合并另一个 CharStat（用于跨设备同步）。

        策略：char_count 系取 max，min/max/ms 取极值，last_seen 取最新。
        """
        if other.char != self.char:
            raise ValueError(
                f"Cannot merge different chars: {self.char} vs {other.char}"
            )

        self.char_count = max(self.char_count, other.char_count)
        self.error_char_count = max(self.error_char_count, other.error_char_count)
        self.total_ms = max(self.total_ms, other.total_ms)
        if other.min_ms > 0 and other.min_ms < self.min_ms:
            self.min_ms = other.min_ms
        self.max_ms = max(self.max_ms, other.max_ms)
        self.last_seen = max(self.last_seen, other.last_seen)
