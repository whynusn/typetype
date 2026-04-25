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

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

from ...application.gateways.score_gateway import ScoreGateway
from ...application.session_context import TypingSessionContext, UploadStatus
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
    keyAccuracyChanged = Signal()
    # 会话状态机信号
    uploadStatusChanged = Signal(int)
    eligibilityReasonChanged = Signal(str)

    def __init__(
        self,
        typing_service: TypingService,
        score_gateway: ScoreGateway,
        score_submitter: "ScoreSubmitter | None" = None,
        time_interval: float = 0.15,
        session_context: TypingSessionContext | None = None,
    ):
        super().__init__()
        self._typing_service = typing_service
        self._score_gateway = score_gateway
        self._score_submitter = score_submitter
        self._session_context = session_context
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

        # 载文模式片索引（None = 非分片模式）
        self._slice_index: int | None = None
        # 分片完成时的 score_data 快照（在 _check_typing_complete 中捕获）
        self._last_slice_stats: dict | None = None

        # 信号发射缓存（避免无变化时重复触发 QML 重新评估）
        self._last_backspace_count = 0
        self._last_correction_count = 0

        # 订阅状态机事件
        if self._session_context:
            self._session_context.subscribe_upload_status(
                self._on_upload_status_changed
            )
            self._session_context.subscribe_eligibility_reason(
                self.eligibilityReasonChanged.emit
            )

    def _match_color_format(self) -> None:
        self._no_fmt.setBackground(QColor("transparent"))
        self._correct_fmt.setBackground(QColor("gray"))
        self._error_fmt.setBackground(QColor("red"))

    def _color_text(self, begin_pos: int, n: int, fmt: QTextCharFormat) -> None:
        if not self._cursor or not self._rich_doc:
            return
        if begin_pos < 0:
            return
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
        self.keyAccuracyChanged.emit()

    def _reset_signal_cache(self) -> None:
        """同步 backspace/correction 缓存，避免 clear() 后重复发射信号。"""
        self._last_backspace_count = self._typing_service.score_data.backspace_count
        self._last_correction_count = self._typing_service.score_data.correction_count

    def _emit_typing_signals(self) -> None:
        self.charNumChanged.emit()
        self.codeLengthChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()
        self.keyAccuracyChanged.emit()
        backspace_count = self._typing_service.score_data.backspace_count
        if backspace_count != self._last_backspace_count:
            self._last_backspace_count = backspace_count
            self.backspaceChanged.emit()
        correction_count = self._typing_service.score_data.correction_count
        if correction_count != self._last_correction_count:
            self._last_correction_count = correction_count
            self.correctionChanged.emit()

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

            # 分片模式：在任何清理之前捕获 score_data 快照
            if self._slice_index is not None:
                s = self._typing_service.score_data
                self._last_slice_stats = {
                    "speed": s.speed,
                    "keyStroke": s.keyStroke,
                    "codeLength": s.codeLength,
                    "accuracy": s.accuracy,
                    "keyAccuracy": s.keyAccuracy,
                    "effectiveSpeed": s.effectiveSpeed,
                    "wrong_char_count": s.wrong_char_count,
                    "backspace_count": s.backspace_count,
                    "correction_count": s.correction_count,
                    "char_count": s.char_count,
                    "key_stroke_count": s.key_stroke_count,
                    "time": s.time,
                }

            # 异步提交成绩到服务器（后台线程，不阻塞 UI）
            # 通知状态机完成当前会话
            if self._session_context:
                self._session_context.complete_typing()
            self._submit_score_async()

            # 必须在 typingEnded.emit() 之前构建 history record，
            # 因为 QML 的 onTypingEnded 回调会同步触发 loadNextSlice →
            # prepare_for_text_load → clear()，清零 time/key_stroke 等数据
            record = self._typing_service.get_history_record()
            if self._slice_index is not None:
                record["slice_index"] = self._slice_index

            self.typingEnded.emit()
            self.historyRecordUpdated.emit(record)
            return True
        return False

    def _submit_score_async(self) -> None:
        """异步提交成绩到服务器（后台线程，不阻塞 UI）。"""
        if self._score_submitter is None:
            return
        # 由状态机决定是否提交
        if self._session_context and not self._session_context.can_submit_score():
            return
        text_id = (
            self._session_context.text_id
            if self._session_context
            else self._typing_service.text_id
        )
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
        """为新一轮载文做准备：停止当前输入并锁定输入区。

        无论是全文载文还是分片载文，都走此方法准备。
        后续 QML 侧 applyLoadedText → handleLoadedText 会完成完整初始化。

        注意：不在此处调用 clear() 归零 char_count/time 等数据。
        原因：QML 侧 lowerPane.text = "" 触发的 onTextChanged 事件是异步的，
        可能在 clear() 之后才执行，此时 char_count 已归零，
        onTextChanged 用旧 growLength 计算出的 begin_pos 会是负数，
        导致 QTextCursor::setPosition 越界。
        清零逻辑统一在 handleLoadedText 中执行，此时新文本已就绪，
        不会有旧 onTextChanged 事件产生负位置。
        """
        self._second_timer.stop()
        self._typing_service.stop()
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
            self.keyAccuracyChanged.emit()

    def handleBackspace(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_backspace()
            self.backspaceChanged.emit()
            self.keyStrokeChanged.emit()
            self.keyAccuracyChanged.emit()

    def handleCorrection(self) -> None:
        if self._typing_service.state.is_started:
            self._typing_service.accumulate_correction()
            self.correctionChanged.emit()
            self.keyStrokeChanged.emit()
            self.keyAccuracyChanged.emit()

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

    @Slot(QQuickTextDocument)
    @Slot(QQuickTextDocument, str)
    def handleLoadedText(self, quick_doc: QQuickTextDocument, text: str = "") -> None:
        if not quick_doc:
            return
        self._rich_doc = quick_doc.textDocument()
        if text:
            self._rich_doc.setPlainText(text)
        plain_doc = self._rich_doc.toPlainText()
        self._cursor = QTextCursor(self._rich_doc)
        # 先 set_total_chars（归零 char_count），再 set_plain_doc（设置文本）
        # 避免 set_plain_doc 触发 onTextChanged 时 char_count 仍为旧值导致负位置
        self._typing_service.set_total_chars(len(plain_doc))
        self._typing_service.set_plain_doc(plain_doc)
        self._typing_service.clear()
        self._reset_signal_cache()
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
        if self._session_context:
            self._session_context.set_text_id(text_id)

    def handleStartStatus(self, status: bool) -> None:
        if self._typing_service.state.is_started != status:
            if status:
                self._typing_service.clear()
                self._reset_signal_cache()
                self._typing_service.start()
                self._second_timer.start()
                if self._session_context:
                    self._session_context.start_typing()
                self.backspaceChanged.emit()
                self.correctionChanged.emit()
            else:
                self._second_timer.stop()
                self._typing_service.stop()
                self._typing_service.clear()
                self._reset_signal_cache()
                self.backspaceChanged.emit()
                self.correctionChanged.emit()
        elif not status:
            self._typing_service.clear()
            self._reset_signal_cache()
            self.backspaceChanged.emit()
            self.correctionChanged.emit()
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
    def key_accuracy(self) -> float:
        return self._typing_service.key_accuracy

    @property
    def char_num(self) -> str:
        return self._typing_service.char_num

    def setCursorPosition(self, new_pos: int):
        self._typing_service.set_cursor_position(new_pos)

    def get_score_message(self) -> str:
        return self._score_gateway.build_score_message(self._typing_service.score_data)

    def copy_score_message(self) -> None:
        self._score_gateway.copy_score_to_clipboard(self._typing_service.score_data)

    def set_slice_index(self, idx: int | None) -> None:
        """设置载文模式的片索引（None = 非分片模式）。"""
        self._slice_index = idx

    def get_last_slice_stats(self) -> dict | None:
        """获取最近一次分片完成时的 score_data 快照。"""
        return self._last_slice_stats

    def build_aggregate_score(self, slice_stats: list[dict], slice_count: int) -> str:
        """计算所有片的聚合成绩，返回 HTML 消息。"""
        return self._score_gateway.build_aggregate_message(slice_stats, slice_count)

    def copy_aggregate_score(self, slice_stats: list[dict], slice_count: int) -> str:
        """计算聚合成绩纯文本并返回（用于剪贴板）。"""
        return self._score_gateway.build_aggregate_plain_text(slice_stats, slice_count)

    # ==========================================
    # 会话状态机代理方法
    # ==========================================

    def setup_network_session(self, text_id: int, source_key: str) -> None:
        """代理：设置网络来源会话。"""
        if self._session_context:
            self._session_context.setup_network_session(text_id, source_key)

    def setup_local_session(self, source_key: str, text_id: int | None = None) -> None:
        """代理：设置本地来源会话。"""
        if self._session_context:
            self._session_context.setup_local_session(source_key, text_id)

    def setup_custom_session(self, source_key: str) -> None:
        """代理：设置自定义文本会话（loadFullText 路径）。"""
        if self._session_context:
            self._session_context.setup_custom_session(source_key)

    def setup_clipboard_session(self) -> None:
        """代理：设置剪贴板会话。"""
        if self._session_context:
            self._session_context.setup_clipboard_session()

    def setup_shuffle_session(self) -> None:
        """代理：设置乱序会话。"""
        if self._session_context:
            self._session_context.setup_shuffle_session()

    def advance_slice(self) -> None:
        """代理：推进到下一片。"""
        if self._session_context:
            self._session_context.advance_slice()

    def is_slice_mode(self) -> bool:
        """代理：当前是否为分片载文模式。"""
        if self._session_context:
            from ...application.session_context import SourceMode

            return self._session_context.source_mode == SourceMode.SLICE
        return False

    @property
    def slice_total(self) -> int:
        """代理：总分片数。"""
        if self._session_context:
            return self._session_context.slice_total
        return 0

    @property
    def slice_index(self) -> int:
        """代理：当前片索引（从1开始）。"""
        if self._session_context:
            return self._session_context.slice_index
        return 0

    def setup_slice_mode(
        self,
        text: str,
        slice_size: int,
        start_slice: int,
        key_stroke_min: int,
        speed_min: int,
        accuracy_min: int,
        pass_count_min: int,
        on_fail_action: str,
    ) -> int:
        """代理：初始化分片载文模式。返回总片数。"""
        if self._session_context:
            return self._session_context.setup_slice_mode(
                text=text,
                slice_size=slice_size,
                start_slice=start_slice,
                key_stroke_min=key_stroke_min,
                speed_min=speed_min,
                accuracy_min=accuracy_min,
                pass_count_min=pass_count_min,
                on_fail_action=on_fail_action,
            )
        return 0

    def get_current_slice_text(self) -> str:
        """代理：返回当前片文本。"""
        if self._session_context:
            return self._session_context.get_current_slice_text()
        return ""

    def get_shuffled_slice_text(self) -> str:
        """代理：返回乱序后的当前片文本。"""
        if self._session_context:
            return self._session_context.get_shuffled_slice_text()
        return ""

    def collect_slice_result(self, stats: dict | None) -> None:
        """代理：收集当前片的 SessionStat 快照。"""
        if self._session_context:
            self._session_context.collect_slice_result(stats)

    def is_last_slice(self) -> bool:
        """代理：当前片是否为最后一片。"""
        if self._session_context:
            return self._session_context.is_last_slice()
        return False

    def should_retype(self) -> bool:
        """代理：检查当前片成绩是否触发重打条件。"""
        if self._session_context:
            return self._session_context.should_retype()
        return False

    @property
    def on_fail_action(self) -> str:
        """代理：未达标时的处理动作。"""
        if self._session_context:
            return self._session_context.on_fail_action
        return "retype"

    def get_slice_status(self) -> str:
        """代理：返回当前片进度摘要。"""
        if self._session_context:
            return self._session_context.get_slice_status()
        return ""

    def get_aggregate_data(self) -> tuple[list[dict], int] | None:
        """代理：返回聚合成绩所需数据。"""
        if self._session_context:
            return self._session_context.get_aggregate_data()
        return None

    def exit_slice_mode(self) -> None:
        """代理：退出载文模式并清理状态。"""
        self.set_slice_index(None)
        if self._session_context:
            self._session_context.exit_slice_mode()

    @property
    def upload_status(self) -> int:
        """当前上传资格状态（int 供 QML 绑定）。"""
        if self._session_context:
            return self._session_context.upload_status.value
        return UploadStatus.NA.value

    @property
    def eligibility_reason(self) -> str:
        """当前资格原因消息。"""
        if self._session_context:
            return self._session_context.get_eligibility_reason()
        return ""

    def _on_upload_status_changed(self, status: UploadStatus) -> None:
        """状态机 upload_status 变化回调。"""
        self.uploadStatusChanged.emit(status.value)
