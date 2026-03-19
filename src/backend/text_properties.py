from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQuick import QQuickTextDocument

from .config.runtime_config import RuntimeConfig
from .domain.auth_service import AuthService
from .domain.text_load_service import TextLoadService
from .domain.typing_service import TypingService
from .integration.global_key_listener import GlobalKeyListener
from .utils.logger import log_info


class Bridge(QObject):
    """QML 通信适配层。

    仅负责：
    - 属性代理（QML 属性绑定 透传到各个 Service）
    - 信号转发（Service 信号 --> Bridge 信号 -> QML）
    - Slot 入口（QML 调用 --> Bridge 调用 -> Service）
    - 全局键盘监听器持有与转发（Wayland 平台特殊处理）
    """

    # ==== 信号定义 ====

    typeSpeedChanged = Signal()
    keyStrokeChanged = Signal()
    codeLengthChanged = Signal()
    charNumChanged = Signal()
    totalTimeChanged = Signal()
    readOnlyChanged = Signal()
    historyRecordUpdated = Signal(dict)
    typingEnded = Signal()
    textLoaded = Signal(str)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()
    loggedinChanged = Signal()
    userInfoChanged = Signal()
    loginResult = Signal(bool, str)
    cursorPosChanged = Signal(int)
    specialPlatformConfirmed = Signal(bool)  # False=normal, True=Wayland special

    def __init__(
        self,
        typing_service: TypingService,
        text_load_service: TextLoadService,
        auth_service: AuthService,
        runtime_config: RuntimeConfig,
        key_listener: GlobalKeyListener | None = None,
    ):
        super().__init__()
        self._typing_service = typing_service
        self._text_load_service = text_load_service
        self._auth_service = auth_service
        self._runtime_config = runtime_config
        self._key_listener = key_listener
        self._is_special_platform = key_listener is not None
        self._lower_pane_focused = False

        self._connect_typing_signals()
        self._connect_text_load_signals()
        self._connect_key_listener()

        self.specialPlatformConfirmed.emit(self._is_special_platform)
        log_info(f"[Bridge] 检测到平台特殊性: {self._is_special_platform}")

    # ==== 信号连接( service 层信号 --> Bridge 层信号 ) ====

    def _connect_typing_signals(self) -> None:
        self._typing_service.typeSpeedChanged.connect(self.typeSpeedChanged.emit)
        self._typing_service.keyStrokeChanged.connect(self.keyStrokeChanged.emit)
        self._typing_service.codeLengthChanged.connect(self.codeLengthChanged.emit)
        self._typing_service.charNumChanged.connect(self.charNumChanged.emit)
        self._typing_service.totalTimeChanged.connect(self.totalTimeChanged.emit)
        self._typing_service.readOnlyChanged.connect(self.readOnlyChanged.emit)
        self._typing_service.typingEnded.connect(self.typingEnded.emit)
        self._typing_service.historyRecordUpdated.connect(
            self.historyRecordUpdated.emit
        )

    def _connect_text_load_signals(self) -> None:
        self._text_load_service.textLoaded.connect(self.textLoaded.emit)
        self._text_load_service.textLoadFailed.connect(self.textLoadFailed.emit)
        self._text_load_service.textLoadingChanged.connect(self.textLoadingChanged.emit)

    def _connect_key_listener(self) -> None:
        if self._key_listener:
            self._key_listener.keyPressed.connect(self.on_key_received)

    def on_key_received(self, keyCode: int, deviceName: str) -> None:
        if self._lower_pane_focused:
            self._typing_service.handlePressed()

    # ==== 属性代理 ====

    @Property(bool, notify=readOnlyChanged)
    def textReadOnly(self) -> bool:
        return self._typing_service.text_read_only

    @Property(bool, notify=textLoadingChanged)
    def textLoading(self) -> bool:
        return self._text_load_service.text_loading

    @Property(str, constant=True)
    def defaultTextSourceKey(self) -> str:
        return self._runtime_config.default_text_source_key

    @Property("QVariantList", constant=True)
    def textSourceOptions(self) -> list:
        return self._runtime_config.get_text_source_options()

    @Property(float, notify=totalTimeChanged)
    def totalTime(self) -> float:
        return self._typing_service.total_time

    @Property(float, notify=typeSpeedChanged)
    def typeSpeed(self) -> float:
        return self._typing_service.type_speed

    @Property(float, notify=keyStrokeChanged)
    def keyStroke(self) -> float:
        return self._typing_service.key_stroke

    @Property(float, notify=codeLengthChanged)
    def codeLength(self) -> float:
        return self._typing_service.code_length

    @Property(int, notify=charNumChanged)
    def wrongNum(self) -> int:
        return self._typing_service.wrong_num

    @Property(str, notify=charNumChanged)
    def charNum(self) -> str:
        return self._typing_service.char_num

    @Property(bool, notify=loggedinChanged)
    def loggedin(self) -> bool:
        return self._auth_service.is_logged_in

    @Property(str, notify=userInfoChanged)
    def userNickname(self) -> str:
        return self._auth_service.current_nickname

    @Property(str, notify=userInfoChanged)
    def currentUser(self) -> str:
        return self._auth_service.current_username

    @Property(bool, notify=specialPlatformConfirmed)
    def isSpecialPlatform(self) -> bool:
        return self._is_special_platform

    # ==== Slot 入口 ====

    @Slot(str)
    def handlePinyin(self, s: str) -> None:
        pass

    @Slot()
    def handlePressed(self) -> None:
        self._typing_service.handlePressed()

    @Slot(bool)
    def setLowerPaneFocused(self, focused: bool) -> None:
        self._lower_pane_focused = focused

    @Slot(str, int)
    def handleCommittedText(self, s: str, growLength: int) -> None:
        self._typing_service.handleCommittedText(s, growLength)

    @Slot(QQuickTextDocument)
    def handleLoadedText(self, quickDoc: QQuickTextDocument) -> None:
        self._typing_service.handleLoadedText(quickDoc)

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        self._text_load_service.requestLoadText(source_key)

    @Slot()
    def loadTextFromClipboard(self) -> None:
        self._text_load_service.loadTextFromClipboard()

    @Slot(bool)
    def handleStartStatus(self, status: bool) -> None:
        self._typing_service.handleStartStatus(status)

    @Slot(result=bool)
    def isStart(self) -> bool:
        return self._typing_service.is_started

    @Slot(result=bool)
    def isReadOnly(self) -> bool:
        return self._typing_service.text_read_only

    @Slot(result=int)
    def getCursorPos(self) -> int:
        return self._typing_service.cursor_position

    @Slot(int)
    def setCursorPos(self, newPos: int):
        self._typing_service.setCursorPosition(newPos)
        self.cursorPosChanged.emit(newPos)

    @Slot(result=str)
    def getScoreMessage(self) -> str:
        return self._typing_service.get_score_message()

    @Slot()
    def copyScoreMessage(self) -> None:
        self._typing_service.copy_score_message()

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        success, message, _ = self._auth_service.login(username, password)
        if success:
            self.loggedinChanged.emit()
            self.userInfoChanged.emit()
        self.loginResult.emit(success, message)

    @Slot()
    def logout(self) -> None:
        self._auth_service.logout()
        self.loggedinChanged.emit()
        self.userInfoChanged.emit()

    def initializeLoginState(self) -> None:
        self._auth_service.initialize()
        if self._auth_service.is_logged_in:
            self.loggedinChanged.emit()
            self.userInfoChanged.emit()
