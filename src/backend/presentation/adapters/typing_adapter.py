"""打字统计 Qt 适配层。

将纯业务逻辑的 TypingService 与 Qt 框架连接。

负责：
- Qt 计时器管理
- 文本着色（QTextCursor）
- 信号发射
- 成绩提交（通过 ScoreSubmitter）

不负责：
- 打字统计逻辑（由 TypingService 负责）
- 状态管理（由 TypingService 负责）
- 字符统计累积（由 TypingService 负责）
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

from ...application.gateways.score_gateway import ScoreGateway
from ...domain.services.typing_service import TypingService
from ...workers.score_submit_worker import ScoreSubmitWorker

if TYPE_CHECKING:
    from ...ports.score_submitter import ScoreSubmitter


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
    backspaceChanged = Signal()
    correctionChanged = Signal()

    def __init__(
        self,
        typing_service: TypingService,
        score_gateway: ScoreGateway,
        score_submitter: "ScoreSubmitter | None" = None,
        time_interval: float = 0.15,
    ):
        super().__init__()
        self._typing_service = typing_service
        self._score_gateway = score_gateway
        self._score_submitter = score_submitter
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

        # 后台线程池
        self._thread_pool = QThreadPool.globalInstance()

    def _match_color_format(self) -> None:
        self._no_fmt.setBackground(QColor("transparent"))
        self._correct_fmt.setBackground(QColor("gray"))
        self._error_fmt.setBackground(QColor("red"))

    def _color_text(self, begin_pos: int, n: int, fmt: QTextCharFormat) -> None:
        if self._cursor and self._rich_doc:
            self._cursor.setPosition(begin_pos)
            self._cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, n
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
            self._typing_service.state.total_chars > 0
            and self._typing_service.state.score_data.char_count
            >= self._typing_service.state.total_chars
            and self._typing_service.state.is_started
        ):
            self._typing_service.stop()
            self._second_timer.stop()
            changed = self._typing_service.set_read_only(True)
            if changed:
                self.readOnlyChanged.emit()
            self._typing_service.flush_char_stats()

            # 异步提交成绩到服务器（后台线程，不阻塞 UI）
            self._submit_score_async()

            self.typingEnded.emit()
            record = self._typing_service.get_history_record()
            self.historyRecordUpdated.emit(record)
            return True
        return False

    def _submit_score_async(self) -> None:
        """异步提交成绩到服务器（后台线程，不阻塞 UI）。"""
        if self._score_submitter is None:
            return
        text_id = self._typing_service.text_id
        if text_id is None or text_id <= 0:
            return  # 纯练习模式或未载文，不提交
        worker = ScoreSubmitWorker(
            score_submitter=self._score_submitter,
            score_data=self._typing_service.score_data,
            text_id=text_id,
        )
        worker.signals.failed.connect(self._on_score_submit_failed)
        self._thread_pool.start(worker)

    def _on_score_submit_failed(self, error_msg: str) -> None:
        """成绩提交失败回调。"""
        from ...utils.logger import log_warning

        log_warning(f"[TypingAdapter] {error_msg}")

    def prepare_for_text_load(self) -> None:
        """为新一轮载文做准备：停止当前输入并锁定输入区。"""
        self._second_timer.stop()
        self._typing_service.stop()
        self._typing_service.clear()
        self._typing_service.set_text_id(None)
        changed = self._typing_service.set_read_only(True)
        if changed:
            self.readOnlyChanged.emit()

    def shuffle_and_prepare(self) -> tuple[str, str] | None:
        """乱序当前文本并准备加载。

        Returns:
            (shuffled_text, title) 元组，或 None（无文本时）。
        """
        import random

        text = self._typing_service.plain_doc
        if not text:
            return None

        chars = list(text)
        random.shuffle(chars)
        shuffled = "".join(chars)
        title = self._typing_service.text_title

        self.prepare_for_text_load()
        return shuffled, title

    # 对外公开的 Slot 方法

    def handlePressed(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_key()
            self.keyStrokeChanged.emit()
            self.codeLengthChanged.emit()

    def handleBackspace(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_backspace()
            self.backspaceChanged.emit()

    def handleCorrection(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_correction()
            self.correctionChanged.emit()

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
        changed = self._typing_service.set_read_only(False)
        if changed:
            self.readOnlyChanged.emit()

    def setTextTitle(self, title: str) -> None:
        """设置当前文本标题（用于上传）。"""
        self._typing_service.set_text_title(title)

    def setTextId(self, text_id: int | None) -> None:
        """设置当前文本ID（用于成绩提交）。"""
        self._typing_service.set_text_id(text_id)

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
    def backspace_count(self) -> int:
        return self._typing_service.backspace_count

    @property
    def correction_count(self) -> int:
        return self._typing_service.correction_count

    @property
    def char_num(self) -> str:
        return self._typing_service.char_num

    def setCursorPosition(self, new_pos: int):
        self._typing_service.set_cursor_position(new_pos)

    def get_score_message(self) -> str:
        return self._score_gateway.build_score_message(self._typing_service.score_data)

    def copy_score_message(self) -> None:
        self._score_gateway.copy_score_to_clipboard(self._typing_service.score_data)
