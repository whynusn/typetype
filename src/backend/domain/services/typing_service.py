"""纯业务逻辑的打字统计服务，无 Qt 依赖。

负责：
- 打字状态管理
- 键数/字数/错误数统计
- 字符统计累积（通过 CharStatsService）

不负责：
- 计时器控制（由 TypingAdapter 负责）
- 文本上色（由 TypingAdapter 负责）
- 信号发射（由 TypingAdapter 负责）
"""

from dataclasses import dataclass, field
from datetime import datetime
from time import time

from ...models.entity.session_stat import SessionStat
from .char_stats_service import CharStatsService


@dataclass
class TypingState:
    """打字会话状态。"""

    score_data: SessionStat = field(
        default_factory=lambda: SessionStat(
            time=0.0,
            key_stroke_count=0,
            char_count=0,
            wrong_char_count=0,
            date="",
        )
    )
    total_chars: int = 0
    cursor_position: int = 0
    is_started: bool = False
    is_read_only: bool = False
    wrong_char_prefix_sum: list[int] = field(default_factory=list)
    last_commit_time_ms: float = 0.0
    plain_doc: str = ""
    text_id: int | None = None
    text_title: str = ""


class TypingService:
    """打字统计服务，纯业务逻辑。

    职责：
    - 管理打字状态（TypingState）
    - 累积键数、字数、错误数
    - 判断打字完成
    - 字符统计累积（通过 CharStatsService）

    不负责：
    - Qt 计时器（由 TypingAdapter 负责）
    - 文本着色（由 TypingAdapter 负责）
    - 信号发射（由 TypingAdapter 负责）
    """

    def __init__(self, char_stats_service: CharStatsService | None = None):
        self._state = TypingState()
        self._char_stats_service = char_stats_service

    @property
    def state(self) -> TypingState:
        return self._state

    @property
    def score_data(self) -> SessionStat:
        return self._state.score_data

    @property
    def type_speed(self) -> float:
        return self._state.score_data.speed

    @property
    def key_stroke(self) -> float:
        return self._state.score_data.keyStroke

    @property
    def code_length(self) -> float:
        return self._state.score_data.codeLength

    @property
    def wrong_num(self) -> int:
        return self._state.score_data.wrong_char_count

    @property
    def backspace_count(self) -> int:
        return self._state.score_data.backspace_count

    @property
    def correction_count(self) -> int:
        return self._state.score_data.correction_count

    @property
    def char_num(self) -> str:
        return f"{self._state.score_data.char_count}/{self._state.total_chars}"

    @property
    def total_time(self) -> float:
        return self._state.score_data.time

    @property
    def text_id(self) -> int | None:
        return self._state.text_id

    @property
    def plain_doc(self) -> str:
        return self._state.plain_doc

    @property
    def text_title(self) -> str:
        return self._state.text_title

    def start(self) -> None:
        """开始打字。"""
        self._state.last_commit_time_ms = time() * 1000
        self._state.is_started = True

    def stop(self) -> None:
        """停止打字。"""
        self._state.is_started = False

    def clear(self) -> None:
        """清空统计数据。

        注意：char_count 和 wrong_char_count 不在此处归零。
        它们由 handle_committed_text 触发更新对应方法隐式归零。
        若在此提前归零，QML 侧尚未完成的 onTextChanged 事件会以 char_count=0
        计算出负数 beginPos，导致 QTextCursor 越界。
        """
        self._state.score_data.time = 0.0
        self._state.score_data.key_stroke_count = 0
        self._state.score_data.backspace_count = 0
        self._state.score_data.correction_count = 0
        self._state.score_data.date = ""
        self._state.last_commit_time_ms = 0.0

    def reset(self) -> None:
        """重置所有状态。"""
        self._state = TypingState()

    def set_total_chars(self, total: int) -> None:
        """设置总字符数。"""
        self._state.total_chars = total
        self._state.score_data.char_count = 0
        self._state.score_data.wrong_char_count = 0
        self._state.wrong_char_prefix_sum = [0 for _ in range(total)]

    def set_plain_doc(self, text: str) -> None:
        """设置目标文本。"""
        self._state.plain_doc = text

    def set_text_id(self, text_id: int | None) -> None:
        """设置当前文本ID。"""
        self._state.text_id = text_id

    def set_text_title(self, title: str) -> None:
        """设置当前文本标题。"""
        self._state.text_title = title

    def set_read_only(self, read_only: bool) -> bool:
        """设置只读状态，返回是否发生变化。"""
        if self._state.is_read_only != read_only:
            self._state.is_read_only = read_only
            return True
        return False

    def set_cursor_position(self, pos: int) -> None:
        """设置光标位置。"""
        self._state.cursor_position = pos

    def accumulate_key(self) -> None:
        """累积键数。"""
        self._state.score_data.key_stroke_count += 1

    def accumulate_backspace(self) -> None:
        """累积退格键按下次数。"""
        self._state.score_data.backspace_count += 1

    def accumulate_correction(self) -> None:
        """累积回改次数（一次删除操作算一次）。"""
        self._state.score_data.correction_count += 1

    def accumulate_time(self, interval: float) -> None:
        """累积时间。"""
        self._state.score_data.time += interval

    def handle_committed_text(
        self, s: str, grow_length: int
    ) -> tuple[list[tuple[int, str, bool]], bool]:
        """处理文本提交事件。

        Args:
            s: 本次提交的子串
            grow_length: 字符数增量（>0 增, <0 删, =0 替换）

        Returns:
            tuple: (char_updates, is_completed)
                char_updates: [(pos, char, is_error), ...] 需要更新的字符列表
                is_completed: 是否打字完成
        """
        char_updates: list[tuple[int, str, bool]] = []
        is_completed = False
        begin_pos = self._state.score_data.char_count + grow_length - len(s)
        now_ms = time() * 1000

        if grow_length > 0:
            # 新增字符
            if self._state.last_commit_time_ms == 0.0:
                self._state.last_commit_time_ms = now_ms
            elapsed_ms = now_ms - self._state.last_commit_time_ms
            per_char_ms = elapsed_ms / max(grow_length, 1)

            for i in range(len(s)):
                pos = begin_pos + i
                if pos >= self._state.total_chars:
                    break
                char = self._state.plain_doc[pos]
                is_error = s[i] != char
                char_updates.append((pos, char, is_error))

                # 更新 prefix_sum
                pre_sum = self._state.wrong_char_prefix_sum[pos - 1] if pos > 0 else 0
                self._state.wrong_char_prefix_sum[pos] = pre_sum + (
                    1 if is_error else 0
                )
                self._state.score_data.wrong_char_count = (
                    self._state.wrong_char_prefix_sum[pos]
                )

                # 累积字符统计
                if self._char_stats_service:
                    self._char_stats_service.accumulate(char, per_char_ms, is_error)

            self._state.last_commit_time_ms = now_ms
            self._state.score_data.char_count += grow_length

            # 检查是否完成
            if (
                self._state.total_chars > 0
                and self._state.score_data.char_count >= self._state.total_chars
                and self._state.is_started
            ):
                is_completed = True
        else:
            # 删除字符 / 纯替换
            for i in range(len(s)):
                if begin_pos + i >= self._state.total_chars:
                    break
                char = self._state.plain_doc[begin_pos + i]
                is_error = s[i] != char
                char_updates.append((begin_pos + i, char, is_error))

                # 更新 prefix_sum
                pre_sum = (
                    self._state.wrong_char_prefix_sum[begin_pos + i - 1]
                    if begin_pos + i > 0
                    else 0
                )
                self._state.wrong_char_prefix_sum[begin_pos + i] = pre_sum + (
                    1 if is_error else 0
                )
                self._state.score_data.wrong_char_count = (
                    self._state.wrong_char_prefix_sum[begin_pos + i]
                )

            # 删除时清除被删除位置
            if grow_length < 0:
                char_count = self._state.score_data.char_count
                for i in range(char_count + grow_length, char_count):
                    char_updates.append((i, "", False))

            self._state.score_data.char_count += grow_length
            self._state.last_commit_time_ms = now_ms

        return char_updates, is_completed

    def flush_char_stats(self) -> None:
        """刷新字符统计。"""
        if self._char_stats_service:
            self._char_stats_service.flush_async()

    def get_history_record(self) -> dict[str, float | int | str]:
        """获取历史记录。"""
        self._state.score_data.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "speed": round(self._state.score_data.speed, 2),
            "keyStroke": round(self._state.score_data.keyStroke, 2),
            "codeLength": round(self._state.score_data.codeLength, 2),
            "wrongNum": self._state.score_data.wrong_char_count,
            "backspaceCount": self._state.score_data.backspace_count,
            "correctionCount": self._state.score_data.correction_count,
            "charNum": self._state.score_data.char_count,
            "time": round(self._state.score_data.time, 2),
            "date": self._state.score_data.date,
        }
