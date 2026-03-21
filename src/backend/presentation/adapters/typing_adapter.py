"""打字统计 Qt 适配层。

将纯业务逻辑的 TypingService 与 Qt 框架连接。

负责：
- Qt 计时器管理
- 文本着色（QTextCursor）
- 信号发射

不负责：
- 打字统计逻辑（由 TypingService 负责）
- 状态管理（由 TypingService 负责）
- 字符统计累积（由 TypingService 负责）
"""

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

from ...application.usecases.typing_usecase import TypingUseCase
from ...domain.services.typing_service import TypingService


class TypingAdapter(QObject):
    """打字统计 Qt 适配层。"""

    # 信号定义
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
        typing_service: TypingService,
        typing_usecase: TypingUseCase,
        time_interval: float = 0.15,
    ):
        super().__init__()
        self._typing_service = typing_service
        self._typing_usecase = typing_usecase
        self.timeInterval = time_interval

        # Qt 相关
        self._rich_doc = None
        self._cursor = None
        self._no_fmt = QTextCharFormat()
        self._correct_fmt = QTextCharFormat()
        self._error_fmt = QTextCharFormat()
        self._match_color_format()

        # 计时器
        self._second_timer = QTimer()
        self._second_timer.timeout.connect(self._accumulate_time)
        self._second_timer.setInterval(int(self.timeInterval * 1000))

    def _match_color_format(self) -> None:
        self._no_fmt.setBackground(QColor("transparent"))
        self._correct_fmt.setBackground(QColor("gray"))
        self._error_fmt.setBackground(QColor("red"))

    def _color_text(self, begin_pos: int, n: int, fmt: QTextCharFormat) -> None:
        if self._cursor and self._rich_doc:
            self._cursor.setPosition(begin_pos)
            self._cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.KeepAnchor, n
            )
            self._cursor.setCharFormat(fmt)

    def _accumulate_time(self) -> None:
        self._typing_service.accumulate_time(self.timeInterval)
        self.totalTimeChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _emit_typing_signals(self) -> None:
        self.charNumChanged.emit()
        self.codeLengthChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _check_typing_complete(self) -> bool:
        if (
            self._typing_service.state.score_data.char_count
            >= self._typing_service.state.total_chars
            and self._typing_service.state.is_started
        ):
            self._typing_service.stop()
            self._second_timer.stop()
            self._typing_service.set_read_only(True)
            self._typing_service.flush_char_stats()
            self.typingEnded.emit()
            record = self._typing_service.get_history_record()
            self.historyRecordUpdated.emit(record)
            return True
        return False

    # 对外公开的 Slot 方法

    def handlePressed(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_key()
            self.keyStrokeChanged.emit()
            self.codeLengthChanged.emit()

    def handleCommittedText(self, s: str, grow_length: int) -> None:
        char_updates, is_completed = self._typing_service.handle_committed_text(
            s, grow_length
        )

        if grow_length > 0:
            # 新增字符：着色
            for pos, char, is_error in char_updates:
                if char:
                    self._color_text(
                        pos, 1, self._correct_fmt if not is_error else self._error_fmt
                    )
            self._emit_typing_signals()
        else:
            # 删除/替换：着色
            for pos, char, is_error in char_updates:
                if char:
                    self._color_text(
                        pos, 1, self._correct_fmt if not is_error else self._error_fmt
                    )
                else:
                    self._color_text(pos, 1, self._no_fmt)
            self._emit_typing_signals()

        if is_completed:
            self._check_typing_complete()

    def handleLoadedText(self, quick_doc: QQuickTextDocument) -> None:
        if quick_doc:
            self._rich_doc = quick_doc.textDocument()
            plain_doc = self._rich_doc.toPlainText()
            self._cursor = QTextCursor(self._rich_doc)
            self._typing_service.set_plain_doc(plain_doc)
            self._typing_service.set_total_chars(len(plain_doc))
        self._typing_service.clear()
        self._typing_service.state.is_started = False
        self._emit_typing_signals()

    def handleStartStatus(self, status: bool) -> None:
        if self._typing_service.state.is_started != status:
            if status:
                self._typing_service.clear()
                self._typing_service.start()
                self._second_timer.start()
            else:
                self._second_timer.stop()
                self._typing_service.stop()
                self._typing_service.clear()
        elif not status:
            self._typing_service.clear()
        changed = self._typing_service.set_read_only(False)
        if changed:
            self.readOnlyChanged.emit()

    @property
    def text_read_only(self) -> bool:
        return self._typing_service.state.is_read_only

    @property
    def score_data(self):
        return self._typing_service.score_data

    @property
    def cursor_position(self) -> int:
        return self._typing_service.state.cursor_position

    @property
    def is_started(self) -> bool:
        return self._typing_service.state.is_started

    @property
    def total_time(self) -> float:
        return self._typing_service.total_time

    @property
    def type_speed(self) -> float:
        return self._typing_service.type_speed

    @property
    def key_stroke(self) -> float:
        return self._typing_service.key_stroke

    @property
    def code_length(self) -> float:
        return self._typing_service.code_length

    @property
    def wrong_num(self) -> int:
        return self._typing_service.wrong_num

    @property
    def char_num(self) -> str:
        return self._typing_service.char_num

    def setCursorPosition(self, new_pos: int):
        self._typing_service.set_cursor_position(new_pos)

    def get_score_message(self) -> str:
        return self._typing_usecase.build_score_message(self._typing_service.score_data)

    def copy_score_message(self) -> None:
        self._typing_usecase.copy_score_to_clipboard(self._typing_service.score_data)
