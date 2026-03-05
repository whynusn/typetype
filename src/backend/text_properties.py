from datetime import datetime

from PySide6.QtCore import Property, QObject, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtQuick import QQuickTextDocument

from .application.usecases.score_usecase import ScoreUseCase
from .application.usecases.text_usecase import TextUseCase
from .config.runtime_config import RuntimeConfig
from .typing.score_data import ScoreData
from .workers.load_text_worker import LoadTextWorker


class Bridge(QObject):
    # 定义多个 Signal，按需发射
    typeSpeedChanged = Signal()
    keyStrokeChanged = Signal()
    codeLengthChanged = Signal()
    # wrongNumChanged = Signal()
    charNumChanged = Signal()
    totalTimeChanged = Signal()
    readOnlyChanged = Signal()
    historyRecordUpdated = Signal(dict)
    typingEnded = Signal()
    textLoaded = Signal(str)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()

    def __init__(
        self,
        text_usecase: TextUseCase,
        score_usecase: ScoreUseCase,
        runtime_config: RuntimeConfig,
    ):
        super().__init__()
        # 底层基础指标
        self._key_num = 0
        self._total_time = 0.0
        self._current_chars = 0
        self._wrong_chars = 0
        self._total_chars = 60
        self._current_cursor_pos = 0
        self._start_status = False
        self._text_read_only = False
        self._rich_doc = None  # QTextDocument 富文本
        self._plain_doc = ""  # 无格式文本
        self._wrong_char_prefix_sum = []  # 错误字数的前缀和数组
        self.timeInterval = 0.2  # 计时器更新间隔（秒）
        self._cursor = None  # 光标位置
        self._score_data = None  # ScoreData 实例（懒加载）
        self._text_loading = False
        self._thread_pool = QThreadPool.globalInstance()
        self._runtime_config = runtime_config
        self._text_usecase = text_usecase
        self._score_usecase = score_usecase

        # 预备文字背景颜色
        self._no_fmt = QTextCharFormat()
        self._correct_fmt = QTextCharFormat()
        self._error_fmt = QTextCharFormat()
        self._match_color_format()

        # 秒数累积计时器
        self.second_timer = QTimer()
        self.second_timer.timeout.connect(self._accumulate_time)
        self.second_timer.setInterval(int(self.timeInterval * 1000))

    def _color_text(self, beginPos, n, fmt):
        """给文本上色"""

        if self._cursor and self._rich_doc:
            self._cursor.setPosition(beginPos)
            self._cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.KeepAnchor, n
            )
            self._cursor.setCharFormat(fmt)

    def _match_color_format(self):
        """配置文字背景色"""
        self._no_fmt.setBackground(QColor("transparent"))
        self._correct_fmt.setBackground(QColor("gray"))
        self._error_fmt.setBackground(QColor("red"))

    def _set_read_only(self, status):
        """设置编辑区文本只读"""
        if self._text_read_only != status:
            self._text_read_only = status
            self.readOnlyChanged.emit()

    def _get_score_data(self) -> ScoreData:
        """获取 ScoreData 实例（懒加载，但只创建一次，后续更新）"""
        if self._score_data is None:
            self._score_data = ScoreData(
                time=self._total_time,
                key_stroke_count=self._key_num,
                char_count=self._current_chars,
                wrong_char_count=self._wrong_chars,
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        return self._score_data

    def _clear_key_num(self):
        """清空键数"""
        self._key_num = 0
        # 同步更新 ScoreData
        if self._score_data is not None:
            self._score_data.key_stroke_count = 0
        # 重新触发 QML 属性更新
        self.codeLengthChanged.emit()
        self.keyStrokeChanged.emit()

    def _accumulate_key_num(self):
        """累积键数"""
        self._key_num += 1
        # 同步更新 ScoreData
        if self._score_data is not None:
            self._score_data.key_stroke_count = self._key_num
        # 重新触发 QML 属性更新
        self.codeLengthChanged.emit()
        self.keyStrokeChanged.emit()

    def _clear_time(self):
        """清空时间"""
        self._total_time = 0.0
        # 同步更新 ScoreData
        if self._score_data is not None:
            self._score_data.time = 0.0
        # 重新触发 QML 属性更新
        self.totalTimeChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _accumulate_time(self):
        """累积时间"""
        self._total_time += self.timeInterval
        # 同步更新 ScoreData
        if self._score_data is not None:
            self._score_data.time = self._total_time
        # 重新触发 QML 属性更新
        self.totalTimeChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

    def _start(self):
        """开始打字"""
        self.second_timer.start()
        self._set_read_only(False)
        self._start_status = True

    def _stop(self):
        """停止打字"""
        self.second_timer.stop()
        self._set_read_only(True)
        self._start_status = False

    def _clear(self):
        """清空数据"""
        self._set_read_only(False)
        self._clear_key_num()
        self._clear_time()
        # 只在清空时销毁 ScoreData 对象
        self._score_data = None

    def _get_new_record(self):
        """获取新的记录"""
        # 更新当前 score_data 的日期为当前时间
        if self._score_data is None:
            # 若无对象，则新建
            self._score_data = self._get_score_data()
        else:
            # 若已有对象，只更新日期
            self._score_data.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self._score_usecase.build_history_record(self._score_data)

    def _update_wrong_num(self, committedString, beginPos):
        """更新错字数"""

        for i in range(len(committedString)):
            if beginPos + i >= self._total_chars:
                break

            realPosition = beginPos + i
            pre_sum = 0  # 记录之前的字有多少个不匹配
            newNotMatch = 0  # 记录当前字是否匹配
            if realPosition > 0:  # 防止越界
                pre_sum = self._wrong_char_prefix_sum[realPosition - 1]
            if committedString[i] != self._plain_doc[realPosition]:  # 检查是否匹配
                newNotMatch = 1

            self._wrong_char_prefix_sum[realPosition] = pre_sum + newNotMatch
            self._wrong_chars = self._wrong_char_prefix_sum[realPosition]

    def _update_current_char_num(self, committedString, growLength, beginPos):
        """更新当前字数"""
        # committedNum = len(committedString) * (1 if isGrowth else -1)

        # 更新当前字数
        self._current_chars += growLength
        self.charNumChanged.emit()

        # 更新错误字数
        self._update_wrong_num(committedString, beginPos)

        # 同步更新 ScoreData
        if self._score_data is not None:
            self._score_data.char_count = self._current_chars
            self._score_data.wrong_char_count = self._wrong_chars
        # 重新触发 QML 属性更新
        self.codeLengthChanged.emit()
        self.typeSpeedChanged.emit()
        self.keyStrokeChanged.emit()

        # 检查是否打完
        if self._current_chars >= self._total_chars and self._start_status:
            self._stop()
            self.typingEnded.emit()
            self.historyRecordUpdated.emit(self._get_new_record())  # 更新历史记录

    def _update_total_char_num(self, totalNum):
        """更新总字数"""
        self._total_chars = totalNum
        self._wrong_char_prefix_sum = [0 for _ in range(totalNum)]
        self.charNumChanged.emit()

    def _set_start_status(self, status):
        """设置开始状态"""
        if status:
            self._clear()
            self._start()
        else:
            self._stop()
            self._clear()

    # 定义只读属性
    @Property(bool, notify=readOnlyChanged)
    def textReadOnly(self):
        """文本只读状态"""
        return self._text_read_only

    @Property(bool, notify=textLoadingChanged)
    def textLoading(self):
        """网络载文是否进行中。"""
        return self._text_loading

    @Property(str, constant=True)
    def defaultTextSourceKey(self):
        """默认网络载文来源 key。"""
        return self._runtime_config.default_text_source_key

    @Property("QVariantList", constant=True)
    def textSourceOptions(self):
        """可选网络载文来源列表。"""
        return self._runtime_config.get_text_source_options()

    @Property(float, notify=totalTimeChanged)
    def totalTime(self):
        """总时间"""
        return self._get_score_data().time

    @Property(float, notify=typeSpeedChanged)
    def typeSpeed(self):
        """打字速度"""
        return self._get_score_data().speed

    @Property(float, notify=keyStrokeChanged)
    def keyStroke(self):
        """击键频率"""
        return self._get_score_data().keyStroke

    @Property(float, notify=codeLengthChanged)
    def codeLength(self):
        """码长"""
        return self._get_score_data().codeLength

    @Property(int, notify=charNumChanged)
    def wrongNum(self):
        """错误字数"""
        return self._get_score_data().wrong_char_count

    @Property(str, notify=charNumChanged)
    def charNum(self):  # 直接返回格式化字符串
        """当前字符数和总字符数"""
        return f"{self._current_chars}/{self._total_chars}"

    @Slot(str)
    def handlePinyin(self, s):
        pass

    @Slot()
    def handlePressed(self):
        """处理按键事件"""
        if self._start_status:
            self._accumulate_key_num()

    @Slot(str, int)
    def handleCommittedText(self, s, growLength):
        """处理提交的文本(可能增也可能删)"""
        beginPos = self._current_chars + growLength - len(s)
        self._update_current_char_num(s, growLength, beginPos)

        # 渲染变动文本
        for i in range(len(s)):
            if beginPos + i >= self._total_chars:
                break

            if s[i] == self._plain_doc[beginPos + i]:
                self._color_text(beginPos + i, 1, self._correct_fmt)
            else:
                self._color_text(beginPos + i, 1, self._error_fmt)

        if growLength < 0:
            for i in range(self._current_chars, self._current_chars - growLength):
                self._color_text(i, 1, self._no_fmt)

    """
    @Slot(str)
    def handleDeletedText(self, s):
        beginPos = self._current_chars - len(s)
        self._update_current_char_num(s, False, beginPos)
        self._color_text(self._current_chars, len(s), self._no_fmt)
    """

    @Slot(QQuickTextDocument)
    def handleLoadedText(self, quickDoc):
        """处理载文内容"""
        if quickDoc:
            self._rich_doc = quickDoc.textDocument()
            plainText = self._rich_doc.toPlainText()
            if plainText == self._plain_doc:
                return  # 检查文本内容是否变化，若无，则不进行后续操作
            self._plain_doc = plainText
            self._cursor = QTextCursor(self._rich_doc)
        self._update_total_char_num(len(self._plain_doc))
        self._set_start_status(False)

    def _set_text_loading(self, loading: bool) -> None:
        if self._text_loading != loading:
            self._text_loading = loading
            self.textLoadingChanged.emit()

    def _request_load_text_from_network(self, source_key: str) -> None:
        """异步处理从网络载文的请求。"""
        if self._text_loading:
            return

        url = self._runtime_config.get_text_source_url(source_key)
        if not url:
            self.textLoadFailed.emit(f"加载文本失败：未知载文来源({source_key})")
            return

        self._set_text_loading(True)
        worker = LoadTextWorker(
            text_usecase=self._text_usecase,
            url=url,
        )
        worker.signals.succeeded.connect(self._on_text_loaded)
        worker.signals.failed.connect(self._on_text_load_failed)
        worker.signals.finished.connect(self._on_text_load_finished)
        self._thread_pool.start(worker)

    def _request_load_text_from_local(self, source_key: str) -> None:
        """同步处理从本地载文的请求。"""
        path = self._runtime_config.get_local_path(source_key)
        if not path:
            self._on_text_load_failed(f"加载文本失败：本地来源缺少路径({source_key})")
            return
        text = self._text_usecase.load_text_from_local(path)
        if text is None:
            self._on_text_load_failed(f"加载文本失败：无法读取本地文章({source_key})")
            return
        self._on_text_loaded(text)

    @Slot(str)
    def requestLoadText(self, source_key: str):
        """按来源 key 统一处理载文请求。"""
        source_type = self._runtime_config.get_text_source_type(source_key)
        if source_type == "network":
            self._request_load_text_from_network(source_key)
            return

        if source_type == "local":
            self._request_load_text_from_local(source_key)
            return

        self._on_text_load_failed(f"加载文本失败：未知载文来源类型({source_key})")

    @Slot(object)
    def _on_text_loaded(self, text: object) -> None:
        if text is None:
            self.textLoadFailed.emit("加载文本失败：未获取到文本")
            return
        if not isinstance(text, str):
            self.textLoadFailed.emit("加载文本失败：返回数据格式错误")
            return
        self.textLoaded.emit(text)

    @Slot(str)
    def _on_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    @Slot()
    def _on_text_load_finished(self) -> None:
        self._set_text_loading(False)

    @Slot()
    def loadTextFromClipboard(self):
        """同步从剪贴板载文。"""
        if self._text_loading:
            return

        self._set_text_loading(True)
        try:
            text = self._text_usecase.load_text_from_clipboard()
            self.textLoaded.emit(text)
        except Exception as e:
            self.textLoadFailed.emit(f"加载文本失败：{str(e)}")
        finally:
            self._set_text_loading(False)

    @Slot(bool)
    def handleStartStatus(self, status):
        """处理开始状态的更改"""
        # print("From", self._start_status, "Set", status)
        if self._start_status != status:
            self._set_start_status(status)
        # 如果是从 False 到 False, 则需清空一遍状态
        elif not status:
            self._clear()

    @Slot(result=bool)
    def isStart(self):
        """获取开始状态"""
        return self._start_status

    @Slot(result=bool)
    def isReadOnly(self):
        """获取只读状态"""
        return self._text_read_only

    @Slot(result=int)
    def getCursorPos(self):
        """获取光标位置"""
        return self._current_cursor_pos

    @Slot(int, result=int)
    def setCursorPos(self, newPos):
        """设置光标位置"""
        self._current_cursor_pos = newPos

    @Slot(result=str)
    def getScoreMessage(self):
        """获取分数信息"""
        return self._score_usecase.build_score_message(self._score_data)

    @Slot()
    def copyScoreMessage(self):
        """复制分数信息到剪贴板"""
        self._score_usecase.copy_score_message(self._score_data)
