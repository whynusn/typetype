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
    def handleLoadedText(self, quickDoc: QQuickTextDocument) -> None:
        self._typing_adapter.handleLoadedText(quickDoc)

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
