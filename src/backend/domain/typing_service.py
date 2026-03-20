from datetime import datetime
from time import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

from ..application.usecases.score_usecase import ScoreUseCase
from ..models.score_data import ScoreData
from .char_stats_service import CharStatsService


class TypingService(QObject):
    """打字统计领域服务。

    负责：
    - ScoreData 状态管理
    - 计时器控制（开始/停止/累积）
    - 键数/字数统计
    - 文本上色逻辑
    - 历史记录构建
    """

    # 信号：供 Bridge 转发到 QML
    typeSpeedChanged = Signal()
    keyStrokeChanged = Signal()
    codeLengthChanged = Signal()
    charNumChanged = Signal()
    totalTimeChanged = Signal()
    typingEnded = Signal()
    readOnlyChanged = Signal()
    historyRecordUpdated = Signal(dict)

    def __init__(
        self,
        score_usecase: ScoreUseCase,
        char_stats_service: CharStatsService,
        time_interval: float = 0.15,
    ):
        super().__init__()
        self._score_data = ScoreData(
            time=0.0,
            key_stroke_count=0,
            char_count=0,
            wrong_char_count=0,
            date="",
        )
        self._score_usecase = score_usecase
        self._char_stats_service = char_stats_service
        self.timeInterval = time_interval

        self._total_chars = 0
        self._cursor_position = 0
        self._start_status = False
        self._text_read_only = False
        self._wrong_char_prefix_sum: list[int] = []

        self._last_commit_time_ms: float = 0.0

        # 文本上色相关
        self._rich_doc = None
        self._cursor = None
        self._plain_doc = ""
        self._no_fmt = QTextCharFormat()
        self._correct_fmt = QTextCharFormat()
        self._error_fmt = QTextCharFormat()
        self._match_color_format()

        # 秒数累积计时器
        self._second_timer = QTimer()
        self._second_timer.timeout.connect(self._accumulate_time)
        self._second_timer.setInterval(int(self.timeInterval * 1000))

    def _set_read_only(self, status: bool) -> None:
        if self._text_read_only != status:
            self._text_read_only = status
            self.readOnlyChanged.emit()

    def _match_color_format(self) -> None:
        """配置文字背景色"""
        self._no_fmt.setBackground(QColor("transparent"))
        self._correct_fmt.setBackground(QColor("gray"))
        self._error_fmt.setBackground(QColor("red"))

    def _color_text(self, beginPos: int, n: int, fmt: QTextCharFormat) -> None:
        """给文本上色"""
        if self._cursor and self._rich_doc:
            self._cursor.setPosition(beginPos)
            self._cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.KeepAnchor, n
            )
            self._cursor.setCharFormat(fmt)

    def _accumulate_key_num(self) -> None:
        """累积键数"""
        self._score_data.key_stroke_count += 1
        self.codeLengthChanged.emit()
        self.keyStrokeChanged.emit()

    def _accumulate_time(self) -> None:
        """累积时间"""
        self._score_data.time += self.timeInterval
        self.totalTimeChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _reset_score_data(self) -> None:
        """将成绩数据归零（不销毁对象）。

        注意：char_count 和 wrong_char_count 不在此处归零。
        它们由 handleCommittedText 触发更新对应方法隐式归零。
        若在此提前归零，QML 侧尚未完成的 onTextChanged 事件会以 char_count=0
        计算出负数 beginPos，导致 QTextCursor 越界。
        """
        self._score_data.time = 0.0
        self._score_data.key_stroke_count = 0
        self._score_data.date = ""

    def _get_new_record(self) -> dict:
        """获取新的记录"""
        self._score_data.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self._score_usecase.build_history_record(self._score_data)

    def _update_wrong_num(self, committedString: str, beginPos: int) -> None:
        """更新错字数"""
        for i in range(len(committedString)):
            if beginPos + i >= self._total_chars:
                break

            realPosition = beginPos + i
            pre_sum = 0
            newNotMatch = 0
            if realPosition > 0:
                pre_sum = self._wrong_char_prefix_sum[realPosition - 1]
            if committedString[i] != self._plain_doc[realPosition]:
                newNotMatch = 1

            self._wrong_char_prefix_sum[realPosition] = pre_sum + newNotMatch
            self._score_data.wrong_char_count = self._wrong_char_prefix_sum[
                realPosition
            ]

    def _update_current_char_num(
        self, committedString: str, growLength: int, beginPos: int
    ) -> None:
        """更新当前字数"""
        self._score_data.char_count += growLength
        self.charNumChanged.emit()

        self._update_wrong_num(committedString, beginPos)

        self.codeLengthChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

        # 检查是否打完
        if self._score_data.char_count >= self._total_chars and self._start_status:
            self._stop()
            self._set_read_only(True)
            self.typingEnded.emit()
            self.historyRecordUpdated.emit(self._get_new_record())

    def _update_total_char_num(self, totalNum: int) -> None:
        """更新总字数"""
        self._total_chars = totalNum
        self._score_data.char_count = 0
        self._score_data.wrong_char_count = 0
        self._wrong_char_prefix_sum = [0 for _ in range(totalNum)]
        self.charNumChanged.emit()

    def _start(self) -> None:
        """开始打字"""
        self._last_commit_time_ms = time() * 1000
        self._second_timer.start()
        self._start_status = True

    def _stop(self) -> None:
        """停止打字"""
        self._second_timer.stop()
        self._start_status = False

    def _update_char_at_pos(self, pos: int, char: str, is_error: bool) -> None:
        """更新单个位置的 wrong_char_prefix_sum 并着色。

        用于 growLength > 0 的合并循环中，将 _update_wrong_num 的
        prefix_sum 计算和 _color_text 的着色合并到一次遍历。
        """
        pre_sum = self._wrong_char_prefix_sum[pos - 1] if pos > 0 else 0
        self._wrong_char_prefix_sum[pos] = pre_sum + (1 if is_error else 0)
        self._score_data.wrong_char_count = self._wrong_char_prefix_sum[pos]
        self._color_text(pos, 1, self._correct_fmt if not is_error else self._error_fmt)

    def _check_typing_complete(self) -> None:
        if self._score_data.char_count >= self._total_chars and self._start_status:
            self._stop()
            self._set_read_only(True)
            self._char_stats_service.flush_async()
            self.typingEnded.emit()
            self.historyRecordUpdated.emit(self._get_new_record())

    def _emit_typing_signals(self) -> None:
        """批量发射打字统计变化信号，通知 QML 更新显示。"""
        self.charNumChanged.emit()
        self.codeLengthChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _clear(self) -> None:
        """清空数据"""
        self._reset_score_data()
        self.codeLengthChanged.emit()
        self.keyStrokeChanged.emit()
        self.totalTimeChanged.emit()
        self.typeSpeedChanged.emit()
        self._last_commit_time_ms = 0.0

    # ── 对外公开的 Slot 方法（供 Bridge 调用） ──

    def handlePressed(self) -> None:
        """处理按键事件"""
        if self._start_status:
            self._accumulate_key_num()

    def handleCommittedText(self, s: str, growLength: int) -> None:
        """处理文本提交事件（增字符 / 删字符 / 替换）。

        @param s: 本次提交的子串（从 beginPos 到文本末尾）
        @param growLength: 字符数增量（>0 增, <0 删, =0 替换）
        """
        # beginPos: 本次提交在目标文本中的起始位置
        beginPos = self._score_data.char_count + growLength - len(s)
        now_ms = time() * 1000

        if growLength > 0:
            # ── 新增字符 ──
            # 计算单字符耗时：总耗时均摊到每个新增字符
            if self._last_commit_time_ms == 0.0:  # 防御性编程，兜底为 0 的情况
                self._last_commit_time_ms = now_ms
            elapsed_ms = now_ms - self._last_commit_time_ms
            per_char_ms = elapsed_ms / growLength

            # 单次遍历完成三件事：char_stats 累积 / prefix_sum 更新 / 着色
            for i in range(len(s)):
                pos = beginPos + i
                if pos >= self._total_chars:
                    break
                char = self._plain_doc[pos]
                is_error = s[i] != char
                if i < growLength:
                    self._char_stats_service.accumulate(char, per_char_ms, is_error)
                # 更新 prefix_sum 并着色（新增 + 已存在的位置都需处理）
                self._update_char_at_pos(pos, char, is_error)

            self._last_commit_time_ms = now_ms
            self._score_data.char_count += growLength
            self._emit_typing_signals()
            self._check_typing_complete()
        else:
            # ── 删除字符 / 纯替换 ──
            # 更新 char_count、wrong_char_prefix_sum，计算错误数
            self._update_current_char_num(s, growLength, beginPos)

            # 重新着色（仅对 s 覆盖的区间）
            for i in range(len(s)):
                if beginPos + i >= self._total_chars:
                    break
                self._color_text(
                    beginPos + i,
                    1,
                    self._correct_fmt
                    if s[i] == self._plain_doc[beginPos + i]
                    else self._error_fmt,
                )

            # 删除时清除被删除位置的着色（char_count 已由 _update_current_char_num 更新）
            if growLength < 0:
                char_count = self._score_data.char_count
                for i in range(char_count, char_count - growLength):
                    self._color_text(i, 1, self._no_fmt)

            self._last_commit_time_ms = now_ms

    def handleLoadedText(self, quickDoc: QQuickTextDocument) -> None:
        """处理载文内容"""
        if quickDoc:
            self._rich_doc = quickDoc.textDocument()
            self._plain_doc = self._rich_doc.toPlainText()
            self._cursor = QTextCursor(self._rich_doc)
        self._update_total_char_num(len(self._plain_doc))
        self._clear()
        self._start_status = False

    def handleStartStatus(self, status: bool) -> None:
        if self._start_status != status:
            if status:
                self._clear()
                self._start()
            else:
                self._stop()
                self._clear()
        elif not status:
            self._clear()
        # 无论开始还是停止，都重置为可编辑状态
        self._set_read_only(False)

    def setCursorPosition(self, newPos: int):
        self._cursor_position = newPos

    # ==== 只读属性 ====
    @property
    def cursor_position(self) -> int:
        return self._cursor_position

    @property
    def text_read_only(self) -> bool:
        return self._text_read_only

    @property
    def score_data(self) -> ScoreData:
        return self._score_data

    @property
    def total_chars(self) -> int:
        return self._total_chars

    @property
    def is_started(self) -> bool:
        return self._start_status

    @property
    def type_speed(self) -> float:
        return self._score_data.speed

    @property
    def key_stroke(self) -> float:
        return self._score_data.keyStroke

    @property
    def code_length(self) -> float:
        return self._score_data.codeLength

    @property
    def wrong_num(self) -> int:
        return self._score_data.wrong_char_count

    @property
    def char_num(self) -> str:
        return f"{self._score_data.char_count}/{self._total_chars}"

    @property
    def total_time(self) -> float:
        return self._score_data.time

    @property
    def char_stats_service(self) -> CharStatsService:
        return self._char_stats_service

    def get_score_message(self) -> str:
        return self._score_usecase.build_score_message(self._score_data)

    def copy_score_message(self) -> None:
        self._score_usecase.copy_score_message(self._score_data)
