"""QML 通信适配层。

仅负责：
- 属性代理（QML 属性绑定透传到各个 Adapter）
- 信号转发（Adapter 信号 -> Bridge 信号 -> QML）
- Slot 入口（QML 调用 -> Bridge 调用 -> Adapter）
- 全局键盘监听器持有与转发（Wayland 平台特殊处理）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQuick import QQuickTextDocument

from ..utils.logger import log_info

# evdev 键码常量（Linux input event codes）
EVDEV_KEY_BACKSPACE = 14

if TYPE_CHECKING:
    from ..integration.global_key_listener import GlobalKeyListener
    from .adapters.auth_adapter import AuthAdapter
    from .adapters.char_stats_adapter import CharStatsAdapter
    from .adapters.leaderboard_adapter import LeaderboardAdapter
    from .adapters.text_adapter import TextAdapter
    from .adapters.typing_adapter import TypingAdapter
    from .adapters.upload_text_adapter import UploadTextAdapter


class Bridge(QObject):
    """QML 通信适配层。"""

    # 信号定义
    typeSpeedChanged = Signal()
    keyStrokeChanged = Signal()
    codeLengthChanged = Signal()
    charNumChanged = Signal()
    totalTimeChanged = Signal()
    readOnlyChanged = Signal()
    historyRecordUpdated = Signal(dict)
    typingEnded = Signal()
    textLoaded = Signal(str, int, str)  # (text_content, text_id, source_label)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()
    loggedinChanged = Signal()
    userInfoChanged = Signal()
    loginResult = Signal(bool, str)
    registerResult = Signal(bool, str)
    loginStateInitialized = Signal(bool)
    cursorPosChanged = Signal(int)
    specialPlatformConfirmed = Signal(bool)
    backspaceChanged = Signal()
    correctionChanged = Signal()
    weakestCharsLoaded = Signal(list)
    leaderboardLoaded = Signal(dict)
    leaderboardLoadFailed = Signal(str)
    leaderboardLoadingChanged = Signal()
    catalogLoaded = Signal(list)
    catalogLoadFailed = Signal(str)
    textListLoaded = Signal(list)
    textListLoadFailed = Signal(str)
    textListLoadingChanged = Signal()
    uploadResult = Signal(bool, str, int)  # (success, message, server_text_id)
    tokenExpired = Signal()
    textIdChanged = Signal()
    # 载文模式信号
    sliceModeChanged = Signal()
    sliceStatusChanged = Signal(str)
    allSlicesCompleted = Signal(str)  # 携带聚合成绩 HTML 消息
    textContentLoaded = Signal(str, str)  # (content, title) - 按 ID 获取的文本内容

    def __init__(
        self,
        typing_adapter: TypingAdapter,
        text_adapter: TextAdapter,
        auth_adapter: AuthAdapter,
        char_stats_adapter: CharStatsAdapter,
        upload_text_adapter: UploadTextAdapter | None = None,
        leaderboard_adapter: LeaderboardAdapter | None = None,
        key_listener: GlobalKeyListener | None = None,
    ):
        super().__init__()
        self._typing_adapter = typing_adapter
        self._text_adapter = text_adapter
        self._auth_adapter = auth_adapter
        self._char_stats_adapter = char_stats_adapter
        self._upload_text_adapter = upload_text_adapter
        self._leaderboard_adapter = leaderboard_adapter
        self._key_listener = key_listener
        self._is_special_platform = key_listener is not None
        self._lower_pane_focused = False
        self._text_id = 0

        # 载文模式状态
        self._slice_mode = False
        self._slices: list[str] = []
        self._current_slice = 0
        self._retype_enabled = False
        self._retype_metric = ""
        self._retype_operator = ""
        self._retype_threshold = 0.0
        self._retype_shuffle = False
        self._slice_stats: list[dict] = []

        self._connect_typing_signals()
        self._connect_text_load_signals()
        self._connect_auth_signals()
        self._connect_char_stats_signals()
        self._connect_upload_signals()
        self._connect_leaderboard_signals()
        self._connect_key_listener()

        self.specialPlatformConfirmed.emit(self._is_special_platform)
        log_info(f"[Bridge] 检测到平台特殊性: {self._is_special_platform}")

    def _connect_typing_signals(self) -> None:
        self._typing_adapter.typeSpeedChanged.connect(self.typeSpeedChanged.emit)
        self._typing_adapter.keyStrokeChanged.connect(self.keyStrokeChanged.emit)
        self._typing_adapter.codeLengthChanged.connect(self.codeLengthChanged.emit)
        self._typing_adapter.charNumChanged.connect(self.charNumChanged.emit)
        self._typing_adapter.totalTimeChanged.connect(self.totalTimeChanged.emit)
        self._typing_adapter.readOnlyChanged.connect(self.readOnlyChanged.emit)
        self._typing_adapter.typingEnded.connect(self.typingEnded.emit)
        self._typing_adapter.historyRecordUpdated.connect(
            self.historyRecordUpdated.emit
        )
        self._typing_adapter.backspaceChanged.connect(self.backspaceChanged.emit)
        self._typing_adapter.correctionChanged.connect(self.correctionChanged.emit)

    def _connect_text_load_signals(self) -> None:
        self._text_adapter.textLoaded.connect(self.textLoaded.emit)
        self._text_adapter.textLoadFailed.connect(self.textLoadFailed.emit)
        self._text_adapter.textLoadingChanged.connect(self.textLoadingChanged.emit)
        self._text_adapter.localTextIdResolved.connect(self._on_local_text_id_resolved)

    def _on_local_text_id_resolved(self, text_id: int) -> None:
        """本地文本异步回查到 text_id 后自动设置。"""
        if text_id and text_id > 0:
            self.setTextId(text_id)

    def _connect_auth_signals(self) -> None:
        self._auth_adapter.loggedinChanged.connect(self.loggedinChanged.emit)
        self._auth_adapter.userInfoChanged.connect(self.userInfoChanged.emit)
        self._auth_adapter.loginResult.connect(self.loginResult.emit)
        self._auth_adapter.registerResult.connect(self.registerResult.emit)
        self._auth_adapter.tokenExpired.connect(self.tokenExpired.emit)
        self._auth_adapter.loginStateInitialized.connect(
            self.loginStateInitialized.emit
        )

    def _connect_char_stats_signals(self) -> None:
        self._char_stats_adapter.weakestCharsLoaded.connect(
            self.weakestCharsLoaded.emit
        )

    def _connect_upload_signals(self) -> None:
        if self._upload_text_adapter:
            self._upload_text_adapter.uploadFinished.connect(self.uploadResult.emit)

    def _connect_leaderboard_signals(self) -> None:
        if self._leaderboard_adapter:
            self._leaderboard_adapter.leaderboardLoaded.connect(
                self.leaderboardLoaded.emit
            )
            self._leaderboard_adapter.leaderboardLoadFailed.connect(
                self.leaderboardLoadFailed.emit
            )
            self._leaderboard_adapter.leaderboardLoadingChanged.connect(
                self.leaderboardLoadingChanged.emit
            )
            self._leaderboard_adapter.textListLoaded.connect(self.textListLoaded.emit)
            self._leaderboard_adapter.textListLoadFailed.connect(
                self.textListLoadFailed.emit
            )
            self._leaderboard_adapter.textListLoadingChanged.connect(
                self.textListLoadingChanged.emit
            )
            self._leaderboard_adapter.catalogLoaded.connect(self.catalogLoaded.emit)
            self._leaderboard_adapter.catalogLoadFailed.connect(
                self.catalogLoadFailed.emit
            )

    def _connect_key_listener(self) -> None:
        if self._key_listener:
            self._key_listener.keyPressed.connect(self.on_key_received)

    def on_key_received(self, keyCode: int, deviceName: str) -> None:
        if self._lower_pane_focused:
            if keyCode == EVDEV_KEY_BACKSPACE:
                self._typing_adapter.handleBackspace()
            self._typing_adapter.handlePressed()

    # 属性代理

    @Property(bool, notify=readOnlyChanged)
    def textReadOnly(self) -> bool:
        return self._typing_adapter.text_read_only

    @Property(bool, notify=textLoadingChanged)
    def textLoading(self) -> bool:
        return self._text_adapter.text_loading

    @Property(str, constant=True)
    def defaultTextSourceKey(self) -> str:
        return self._text_adapter.get_default_source_key()

    @Property(str, constant=True)
    def defaultTextTitle(self) -> str:
        return self._text_adapter.get_default_source_label()

    @Property(list, constant=True)
    def textSourceOptions(self) -> list:
        return self._text_adapter.get_source_options()

    @Property(list, constant=True)
    def rankingSourceOptions(self) -> list:
        return self._text_adapter.get_ranking_source_options()

    @Property(list, constant=True)
    def uploadTextSourceOptions(self) -> list:
        return self._text_adapter.get_upload_source_options()

    @Property(float, notify=totalTimeChanged)
    def totalTime(self) -> float:
        return self._typing_adapter.total_time

    @Property(float, notify=typeSpeedChanged)
    def typeSpeed(self) -> float:
        return self._typing_adapter.type_speed

    @Property(float, notify=keyStrokeChanged)
    def keyStroke(self) -> float:
        return self._typing_adapter.key_stroke

    @Property(float, notify=codeLengthChanged)
    def codeLength(self) -> float:
        return self._typing_adapter.code_length

    @Property(int, notify=charNumChanged)
    def wrongNum(self) -> int:
        return self._typing_adapter.wrong_num

    @Property(int, notify=backspaceChanged)
    def backspace(self) -> int:
        return self._typing_adapter.backspace_count

    @Property(int, notify=correctionChanged)
    def correction(self) -> int:
        return self._typing_adapter.correction_count

    @Property(str, notify=charNumChanged)
    def charNum(self) -> str:
        return self._typing_adapter.char_num

    @Property(bool, notify=loggedinChanged)
    def loggedin(self) -> bool:
        return self._auth_adapter.loggedin

    @Property(str, notify=userInfoChanged)
    def userNickname(self) -> str:
        return self._auth_adapter.user_nickname

    @Property(str, notify=userInfoChanged)
    def currentUser(self) -> str:
        return self._auth_adapter.current_user

    @Property(bool, notify=specialPlatformConfirmed)
    def isSpecialPlatform(self) -> bool:
        return self._is_special_platform

    @Property(bool, notify=leaderboardLoadingChanged)
    def leaderboardLoading(self) -> bool:
        if self._leaderboard_adapter:
            return self._leaderboard_adapter.loading
        return False

    @Property(bool, notify=textListLoadingChanged)
    def textListLoading(self) -> bool:
        if self._leaderboard_adapter:
            return self._leaderboard_adapter.text_list_loading
        return False

    @Property(int, notify=textIdChanged)
    def textId(self) -> int:
        return self._text_id

    # Slot 入口

    @Slot(str)
    def handlePinyin(self, s: str) -> None:
        pass

    @Slot()
    def handlePressed(self) -> None:
        self._typing_adapter.handlePressed()

    @Slot()
    def accumulateCorrection(self) -> None:
        self._typing_adapter.handleCorrection()

    @Slot()
    def accumulateBackspace(self) -> None:
        self._typing_adapter.handleBackspace()

    @Slot(bool)
    def setLowerPaneFocused(self, focused: bool) -> None:
        self._lower_pane_focused = focused

    @Slot(str, int)
    def handleCommittedText(self, s: str, growLength: int) -> None:
        self._typing_adapter.handleCommittedText(s, growLength)

    @Slot(QQuickTextDocument)
    @Slot(QQuickTextDocument, str)
    def handleLoadedText(self, quickDoc: QQuickTextDocument, text: str = "") -> None:
        self._typing_adapter.handleLoadedText(quickDoc, text)

    @Slot(str)
    def setTextTitle(self, title: str) -> None:
        """设置当前文本标题（用于上传）。"""
        self._typing_adapter.setTextTitle(title)

    @Slot(int)
    def setTextId(self, text_id: int) -> None:
        """设置当前文本ID（用于成绩提交）。"""
        self._text_id = text_id
        self._typing_adapter.setTextId(text_id if text_id > 0 else None)
        self.textIdChanged.emit()

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        self._typing_adapter.prepare_for_text_load()
        self._text_adapter.requestLoadText(source_key)

    @Slot()
    def loadTextFromClipboard(self) -> None:
        self._typing_adapter.prepare_for_text_load()
        self._text_adapter.loadTextFromClipboard()

    @Slot(str, str, str, bool, bool)
    def uploadText(
        self, title: str, content: str, sourceKey: str, toLocal: bool, toCloud: bool
    ) -> None:
        """上传文本，支持同时上传到本地和云端。"""
        if not self._upload_text_adapter:
            self.uploadResult.emit(False, "上传功能未初始化", 0)
            return
        self._upload_text_adapter.upload(title, content, sourceKey, toLocal, toCloud)

    @Slot(bool)
    def handleStartStatus(self, status: bool) -> None:
        self._typing_adapter.handleStartStatus(status)

    @Slot(result=bool)
    def isStart(self) -> bool:
        return self._typing_adapter.is_started

    @Slot(result=bool)
    def isReadOnly(self) -> bool:
        return self._typing_adapter.text_read_only

    @Slot(result=int)
    def getCursorPos(self) -> int:
        return self._typing_adapter.cursor_position

    @Slot(int)
    def setCursorPos(self, newPos: int):
        self._typing_adapter.setCursorPosition(newPos)
        self.cursorPosChanged.emit(newPos)

    @Slot(result=str)
    def getScoreMessage(self) -> str:
        return self._typing_adapter.get_score_message()

    @Slot()
    def copyScoreMessage(self) -> None:
        self._typing_adapter.copy_score_message()

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        self._auth_adapter.login(username, password)

    @Slot(str, str, str)
    def register(self, username: str, password: str, nickname: str = "") -> None:
        self._auth_adapter.register(username, password, nickname)

    @Slot()
    def logout(self) -> None:
        self._auth_adapter.logout()

    def initializeLoginState(self) -> None:
        self._auth_adapter.initialize_login_state()

    @Slot()
    def checkTokenStatus(self) -> None:
        """应用从后台恢复时检查 token 状态。"""
        self._auth_adapter.check_token_status()

    @Slot()
    @Slot(int)
    @Slot(int, str)
    @Slot(int, str, "QVariantMap")
    def loadWeakChars(self, n=10, sortMode="error_rate", weights=None):
        self._char_stats_adapter.loadWeakChars(
            n=n,
            sort_mode=sortMode,
            weights=weights if weights else None,
        )

    @Slot(str)
    def loadLeaderboard(self, source_key: str) -> None:
        """加载指定来源的排行榜。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadLeaderboard(source_key)

    @Slot(int)
    def loadLeaderboardByTextId(self, text_id: int) -> None:
        """按 text_id 直接加载排行榜。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadLeaderboardByTextId(text_id)

    @Slot(str)
    def loadTextList(self, source_key: str) -> None:
        """加载来源下的文本列表。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadTextList(source_key)

    @Slot(str)
    def requestLoadTextForPreview(self, source_key: str) -> None:
        """为载文 Dialog 预览加载文本（不触发打字流程）。

        与 requestLoadText 不同，此方法不调用 prepare_for_text_load，
        不清状态、不停计时。文本内容通过 textLoaded 信号返回。
        """
        self._text_adapter.requestLoadText(source_key)

    @Slot(int)
    def getTextContentById(self, text_id: int) -> None:
        """按文本 ID 异步获取完整内容。结果通过 textContentLoaded 信号返回。"""
        if not self._leaderboard_adapter:
            return
        from ..workers.text_content_worker import TextContentWorker

        gateway = self._leaderboard_adapter._leaderboard_gateway
        worker = TextContentWorker(leaderboard_gateway=gateway, text_id=text_id)
        worker.signals.succeeded.connect(self._on_text_content_loaded)
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(worker)

    def _on_text_content_loaded(self, data: dict) -> None:
        content = data.get("content", "")
        title = data.get("title", "")
        self.textContentLoaded.emit(content or "", title or "")

    @Slot()
    def loadCatalog(self) -> None:
        """从服务端加载文本来源目录。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadCatalog()

    @Slot()
    def refreshCatalog(self) -> None:
        """清除缓存并重新从服务端加载文本来源目录。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.refreshCatalog()

    @Slot()
    def requestShuffle(self) -> None:
        """乱序当前文本。

        将当前文本的所有字符随机打乱，重置打字状态。
        乱序后的文本不参与排行榜（text_id 清空）。
        """
        result = self._typing_adapter.shuffle_and_prepare()
        if not result:
            return

        shuffled, title = result
        # 清空 text_id：乱序内容与服务端不匹配，不提交成绩
        self._text_id = 0
        self._typing_adapter.setTextId(None)
        self.textIdChanged.emit()
        # 发射 textLoaded 信号，QML 侧 applyLoadedText + handleLoadedText 重置打字状态
        self.textLoaded.emit(shuffled, -1, title)

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        """复制文本到剪贴板。"""
        from PySide6.QtGui import QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    # ==========================================
    # 载文模式
    # ==========================================

    @Property(bool, notify=sliceModeChanged)
    def sliceMode(self) -> bool:
        return self._slice_mode

    @Property(int, constant=True)
    def totalSliceCount(self) -> int:
        return len(self._slices)

    @Slot(str, int, bool, str, str, float, bool)
    def setupSliceMode(
        self,
        text: str,
        slice_size: int,
        retype_enabled: bool,
        metric: str,
        operator: str,
        threshold: float,
        shuffle: bool,
    ) -> None:
        """初始化载文模式：分片文本并加载第一片。

        Args:
            text: 原始文本
            slice_size: 每片字数
            retype_enabled: 是否开启重打条件
            metric: 重打指标 (speed/accuracy/wrong_char_count)
            operator: 比较符 (lt/le/ge/gt)
            threshold: 重打阈值
            shuffle: 重打时是否乱序
        """
        if not text or slice_size <= 0:
            return

        # 分片
        self._slices = []
        for i in range(0, len(text), slice_size):
            self._slices.append(text[i : i + slice_size])

        if not self._slices:
            return

        self._current_slice = 0
        self._retype_enabled = retype_enabled
        self._retype_metric = metric
        self._retype_operator = operator
        self._retype_threshold = threshold
        self._retype_shuffle = shuffle
        self._slice_stats = []
        self._slice_mode = True
        self.sliceModeChanged.emit()

        self.sliceStatusChanged.emit(f"载文模式: 第 1/{len(self._slices)} 片")

        # 加载第一片
        self._load_current_slice()

    def _load_current_slice(self) -> None:
        """加载当前片到打字区。"""
        if self._current_slice >= len(self._slices):
            return

        slice_text = self._slices[self._current_slice]
        idx = self._current_slice + 1
        total = len(self._slices)

        # 设置片索引（注入到 historyRecordUpdated 的 record 中）
        self._typing_adapter.set_slice_index(idx)

        # 准备载文（只停计时和锁定，不清统计数据）
        self._typing_adapter.prepare_for_slice_load()

        # 清空 text_id（分片不提交成绩）
        self._text_id = 0
        self._typing_adapter.setTextId(None)
        self.textIdChanged.emit()

        # 发射 textLoaded，QML 侧完成 applyLoadedText + handleLoadedText
        label = f"载文 {idx}/{total}"
        self.textLoaded.emit(slice_text, -1, label)

    @Slot()
    def collectSliceResult(self) -> None:
        """收集当前片的 SessionStat 快照。"""
        stats = self._typing_adapter.get_last_slice_stats()
        if not stats:
            return
        self._slice_stats.append(stats)

        idx = self._current_slice + 1
        total = len(self._slices)
        status = (
            f"载文模式: 第 {idx}/{total} 片"
            f"  |  上一片: {stats['speed']:.0f}CPM {stats['accuracy']:.1f}%"
        )
        self.sliceStatusChanged.emit(status)

    @Slot(result=bool)
    def isLastSlice(self) -> bool:
        """当前片是否为最后一片。"""
        return self._current_slice >= len(self._slices) - 1

    @Slot()
    def loadNextSlice(self) -> None:
        """载入下一片。"""
        if self._current_slice < len(self._slices) - 1:
            self._current_slice += 1
            self._load_current_slice()

    @Slot(result=bool)
    def shouldRetype(self) -> bool:
        """检查当前片成绩是否触发重打条件。"""
        if not self._retype_enabled or not self._slice_stats:
            return False

        last = self._slice_stats[-1]
        value = last.get(self._retype_metric, 0)

        ops = {
            "lt": lambda v, t: v < t,
            "le": lambda v, t: v <= t,
            "ge": lambda v, t: v >= t,
            "gt": lambda v, t: v > t,
        }
        op_func = ops.get(self._retype_operator)
        if not op_func:
            return False
        return op_func(value, self._retype_threshold)

    @Slot()
    def handleSliceRetype(self) -> None:
        """根据重打配置自动处理重打（原样或乱序）。"""
        if self._retype_shuffle:
            self.shuffleCurrentSlice()
        else:
            self._reload_current_slice()

    def _reload_current_slice(self) -> None:
        """重打当前片（原样重新加载）。"""
        self._load_current_slice()

    @Slot()
    def shuffleCurrentSlice(self) -> None:
        """乱序当前片并加载。"""
        import random

        if self._current_slice >= len(self._slices):
            return

        chars = list(self._slices[self._current_slice])
        random.shuffle(chars)
        shuffled = "".join(chars)

        idx = self._current_slice + 1
        total = len(self._slices)
        self._typing_adapter.set_slice_index(idx)
        self._typing_adapter.prepare_for_slice_load()
        self._text_id = 0
        self._typing_adapter.setTextId(None)
        self.textIdChanged.emit()
        self.textLoaded.emit(shuffled, -1, f"载文 {idx}/{total}（乱序）")

    @Slot(result=str)
    def buildAggregateScore(self) -> str:
        """计算所有片的聚合成绩，返回 HTML 消息。"""
        if not hasattr(self, "_typing_adapter") or not self._typing_adapter:
            return ""
        score_gateway = self._typing_adapter._score_gateway
        return score_gateway.build_aggregate_message(
            self._slice_stats, len(self._slices)
        )

    @Slot()
    def copyAggregateScore(self) -> None:
        """复制聚合成绩到剪贴板。"""
        score_gateway = self._typing_adapter._score_gateway
        text = score_gateway.build_aggregate_plain_text(
            self._slice_stats, len(self._slices)
        )
        if text:
            self.copyToClipboard(text)

    @Slot()
    def exitSliceMode(self) -> None:
        """退出载文模式，清理状态。"""
        self._slice_mode = False
        self._slices = []
        self._current_slice = 0
        self._slice_stats = []
        self._retype_enabled = False
        self._typing_adapter.set_slice_index(None)
        self.sliceModeChanged.emit()
        self.sliceStatusChanged.emit("")

    @Slot(result=str)
    def getSliceStatus(self) -> str:
        """返回当前片进度摘要。"""
        if not self._slice_mode:
            return ""
        total = len(self._slices)
        idx = self._current_slice + 1
        return f"载文模式: 第 {idx}/{total} 片"

    @Slot(result="QVariantMap")
    def getLastSliceStats(self) -> dict:
        """返回最后一片的成绩快照。"""
        if not self._slice_stats:
            return {}
        return self._slice_stats[-1]
