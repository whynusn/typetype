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
from ...utils.logger import log_debug
from .char_stats_service import CharStatsService

# 标顶排除标点集——输入法使用标点符号把首选字顶上屏时，
# 标点字符不应参与打词率计算。
# 参考：TypeSunny Score.AddInputStack() 的 ExcludePuncts
EXCLUDE_PUNCTS: frozenset[str] = frozenset(
    "~!@#$%^&*()_+|}{\":?><`[]\\;',./"
    "~！@#￥%……&*（）——+{}|：“”《》？·、【】；‘’，。"
    "…—"  # 省略号、破折号（WPF 特殊处理）
)


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
    wrong_char_prefix_sum: dict[int, int] = field(default_factory=dict)
    last_commit_time_ms: float = 0.0
    plain_doc: str = ""
    text_id: int | None = None
    text_title: str = ""
    peak_speed: float = 0.0
    peak_key_stroke: float = 0.0
    peak_code_length: float = float("inf")
    char_commit_times: dict[int, float] = field(default_factory=dict)
    phrase_positions: set[int] = field(default_factory=set)


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
        self._word_detection_enabled = True

    @property
    def word_detection_enabled(self) -> bool:
        return self._word_detection_enabled

    @word_detection_enabled.setter
    def word_detection_enabled(self, value: bool) -> None:
        self._word_detection_enabled = value

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
    def key_accuracy(self) -> float:
        return self._state.score_data.keyAccuracy

    @property
    def char_num(self) -> str:
        return f"{self._state.score_data.char_count}/{self._state.total_chars}"

    @property
    def typing_progress(self) -> float:
        if self._state.total_chars <= 0:
            return 0.0
        return self._state.score_data.char_count / self._state.total_chars

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

    @property
    def peak_speed(self) -> float:
        return self._state.peak_speed

    @property
    def peak_key_stroke(self) -> float:
        return self._state.peak_key_stroke

    @property
    def peak_code_length(self) -> float:
        return self._state.peak_code_length

    def update_peaks(self) -> None:
        s = self._state.score_data
        if s.time <= 0:
            return
        if s.speed > self._state.peak_speed:
            self._state.peak_speed = s.speed
        if s.keyStroke > self._state.peak_key_stroke:
            self._state.peak_key_stroke = s.keyStroke
        if s.char_count > 0 and s.codeLength < self._state.peak_code_length:
            self._state.peak_code_length = s.codeLength

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
        self._state.score_data.slow_chars = []
        self._state.score_data.biao_ding_count = 0
        self._state.score_data.peak_speed = 0.0
        self._state.score_data.peak_key_stroke = 0.0
        self._state.score_data.peak_code_length = 0.0
        self._state.last_commit_time_ms = 0.0
        self._state.char_commit_times.clear()
        self._state.phrase_positions.clear()
        if self._char_stats_service:
            self._char_stats_service.clear()

    def reset(self) -> None:
        """重置所有状态。"""
        self._state = TypingState()

    def set_total_chars(self, total: int) -> None:
        """设置总字符数。"""
        self._state.total_chars = total
        self._state.score_data.char_count = 0
        self._state.score_data.wrong_char_count = 0
        self._state.wrong_char_prefix_sum = {}
        self._state.peak_speed = 0.0
        self._state.peak_key_stroke = 0.0
        self._state.peak_code_length = float("inf")

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

    @staticmethod
    def _count_non_punct(text: str) -> int:
        """统计文本中非标点字符数（用于标顶场景的打词判定）。"""
        return sum(1 for c in text if c not in EXCLUDE_PUNCTS)

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
        if begin_pos < 0:
            return char_updates, is_completed
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
                pre_sum = (
                    self._state.wrong_char_prefix_sum.get(pos - 1, 0) if pos > 0 else 0
                )
                self._state.wrong_char_prefix_sum[pos] = pre_sum + (
                    1 if is_error else 0
                )
                self._state.score_data.wrong_char_count = (
                    self._state.wrong_char_prefix_sum.get(pos, 0)
                )

                # 记录每个字符的提交时间（毫秒时间戳）
                self._state.char_commit_times[pos] = now_ms
                # 标记词组位置：使用 TypeSunny 的 AddInputStack 逻辑——
                # 当一次提交中包含 ≥2 个非标点字符时，所有非标点字符标记为"词组"
                # 标点字符完全不参与打词率计算（排除标顶干扰）
                non_punct_count = self._count_non_punct(s)
                is_phrase = (
                    self._word_detection_enabled
                    and grow_length > 1
                    and pos >= self._state.score_data.char_count
                    and non_punct_count >= 2
                    and s[i] not in EXCLUDE_PUNCTS
                )
                if is_phrase:
                    self._state.phrase_positions.add(pos)
                log_debug(
                    f"[TypingService] handle_committed_text: "
                    f"s='{s}' grow_length={grow_length} begin_pos={begin_pos} "
                    f"pos={pos} char='{char}' char_count_before={self._state.score_data.char_count} "
                    f"elapsed_ms={elapsed_ms:.0f} per_char_ms={per_char_ms:.0f} "
                    f"is_phrase={is_phrase} phrase_positions={sorted(self._state.phrase_positions)}"
                )
                # 累积字符统计
                if self._char_stats_service:
                    self._char_stats_service.accumulate(char, per_char_ms, is_error)

            self._state.last_commit_time_ms = now_ms
            self._state.score_data.char_count += grow_length

            # 检测标顶事件：批量提交文本且末字符为标点时计数为一次标顶
            if grow_length > 1 and s and s[-1] in EXCLUDE_PUNCTS:
                self._state.score_data.biao_ding_count += 1

            # 检查是否完成
            if (
                self._state.total_chars > 0
                and self._state.score_data.char_count >= self._state.total_chars
                and self._state.is_started
            ):
                # 如果最后一个字正确则完成，否则允许回改（Issue #2）
                last_pos = self._state.total_chars - 1
                prev_wrong = self._state.wrong_char_prefix_sum.get(last_pos - 1, 0)
                last_wrong = self._state.wrong_char_prefix_sum.get(last_pos, prev_wrong)
                if last_wrong == prev_wrong:
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
                    self._state.wrong_char_prefix_sum.get(begin_pos + i - 1, 0)
                    if begin_pos + i > 0
                    else 0
                )
                self._state.wrong_char_prefix_sum[begin_pos + i] = pre_sum + (
                    1 if is_error else 0
                )
                self._state.score_data.wrong_char_count = (
                    self._state.wrong_char_prefix_sum.get(begin_pos + i, 0)
                )

            # 删除时清除被删除位置
            if grow_length < 0:
                char_count = self._state.score_data.char_count
                for i in range(char_count + grow_length, char_count):
                    char_updates.append((i, "", False))
                    self._state.phrase_positions.discard(i)
                self._state.last_commit_time_ms = now_ms

            self._state.score_data.char_count += grow_length
            # NOTE: grow_length=0（纯替换）时不更新 last_commit_time_ms，
            # 避免输入法 preedit 变化等无意义事件重置时间基准

        return char_updates, is_completed

    def flush_char_stats(self) -> None:
        """刷新字符统计。"""
        if self._char_stats_service:
            self._char_stats_service.flush_async()

    def capture_slow_chars(self) -> None:
        """捕获慢字条目到 score_data 中。

        必须在 flush_char_stats() 之前调用，否则 _dirty 被清空后无法获取。
        """
        if self._char_stats_service:
            log_debug(
                f"[TypingService] capture_slow_chars: "
                f"plain_doc='{self._state.plain_doc}' "
                f"phrase_positions={sorted(self._state.phrase_positions)}"
            )
            self._state.score_data.slow_chars = (
                self._char_stats_service.get_slow_entries(
                    self._state.plain_doc,
                    phrase_positions=self._state.phrase_positions,
                )
            )
            log_debug(
                f"[TypingService] capture_slow_chars result: {self._state.score_data.slow_chars}"
            )

    def get_history_record(self) -> dict[str, float | int | str | list]:
        """获取历史记录。

        NOTE: slow_chars 可能已由外部在 flush_char_stats() 之前捕获到
        score_data.slow_chars 中（见 TypingAdapter._check_typing_complete）。
        优先使用预捕获值，避免 flush 后 _dirty 为空导致数据丢失。
        """
        self._state.score_data.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        word_typing_rate = self._compute_word_typing_rate()
        self._state.score_data.word_typing_rate = word_typing_rate
        slow_chars = self._state.score_data.slow_chars or []
        if not slow_chars and self._char_stats_service:
            slow_chars = self._char_stats_service.get_slow_entries(
                self._state.plain_doc,
                phrase_positions=self._state.phrase_positions,
            )
        return {
            "speed": round(self._state.score_data.speed, 2),
            "keyStroke": round(self._state.score_data.keyStroke, 2),
            "codeLength": round(self._state.score_data.codeLength, 2),
            "wrongNum": self._state.score_data.wrong_char_count,
            "correctionCount": self._state.score_data.correction_count,
            "backspaceCount": self._state.score_data.backspace_count,
            "keyAccuracy": round(self._state.score_data.keyAccuracy, 2),
            "charNum": self._state.score_data.char_count,
            "time": round(self._state.score_data.time, 2),
            "date": self._state.score_data.date,
            "peakSpeed": round(self._state.peak_speed, 2),
            "peakKeyStroke": round(self._state.peak_key_stroke, 2),
            "peakCodeLength": round(self._state.peak_code_length, 2)
            if self._state.peak_code_length != float("inf")
            else 0.0,
            "slowChars": slow_chars,
            "wordTypingRate": word_typing_rate,
            "biaoDingCount": self._state.score_data.biao_ding_count,
        }

    def _compute_word_typing_rate(self) -> float:
        """计算打词率：词组字符数 / 总已输入字符数 × 100。

        词组判定基于文本长度变化（grow_length > 1），而非时间间隔。
        分母为当前已输入的全部字符（含标点、英文、数字），
        符合「打词数占总字数比率」的直觉定义。

        word_detection_enabled 为 False 时始终返回 0.0（用于标顶等
        会批量提交单字的输入法，避免误判）。
        """
        if not self._word_detection_enabled:
            return 0.0

        phrase = self._state.phrase_positions
        total_input = self._state.score_data.char_count

        log_debug(
            f"[TypingService] _compute_word_typing_rate: "
            f"total_input={total_input} phrase_positions={sorted(phrase)}"
        )

        if total_input <= 0 or not phrase:
            log_debug(
                "[TypingService] _compute_word_typing_rate: no input or no phrases → 0.0"
            )
            return 0.0

        word_chars = sum(1 for pos in phrase if pos < total_input)

        log_debug(
            f"[TypingService] _compute_word_typing_rate: "
            f"total_input={total_input} word_chars={word_chars}"
        )

        rate = round(word_chars / total_input * 100, 2)
        log_debug(f"[TypingService] _compute_word_typing_rate: result={rate}%")
        return rate
