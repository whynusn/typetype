from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ...domain.services.auth_service import AuthService
from ...utils.logger import log_info, log_warning


class AuthAdapter(QObject):
    loggedinChanged = Signal()
    userInfoChanged = Signal()
    loginResult = Signal(bool, str)
    tokenExpired = Signal()
    tokenRefreshed = Signal()

    RETRY_INTERVAL_MS = 60000
    MAX_RETRY = 10
    REFRESH_AHEAD_SECONDS = 120

    def __init__(self, auth_service: AuthService):
        super().__init__()
        self._auth_service = auth_service
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._retry_count = 0

    @property
    def loggedin(self) -> bool:
        return self._auth_service.is_logged_in

    @property
    def current_user(self) -> str:
        return self._auth_service.current_username

    @property
    def user_nickname(self) -> str:
        return self._auth_service.current_nickname

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        success, message, _ = self._auth_service.login(username, password)
        if success:
            self.loggedinChanged.emit()
            self.userInfoChanged.emit()
            self._start_refresh_timer()
        self.loginResult.emit(success, message)

    @Slot()
    def logout(self) -> None:
        self._refresh_timer.stop()
        self._retry_count = 0
        self._auth_service.logout()
        self.loggedinChanged.emit()
        self.userInfoChanged.emit()

    def initialize_login_state(self) -> None:
        self._auth_service.initialize()
        if self._auth_service.is_logged_in:
            self.loggedinChanged.emit()
            self.userInfoChanged.emit()
            self._start_refresh_timer()

    def _start_refresh_timer(self) -> None:
        interval = self._auth_service.refresh_interval_seconds
        if interval <= 0:
            log_warning("[AuthAdapter] 无有效 expires_in，不启动定时刷新")
            return
        self._retry_count = 0
        ms = interval * 1000
        self._refresh_timer.start(ms)
        log_info(f"[AuthAdapter] 定时刷新已启动，间隔 {interval}s")

    def _on_refresh_timer(self) -> None:
        if not self._auth_service.is_logged_in:
            return

        success, _ = self._auth_service.refresh_token()
        if success:
            log_info("[AuthAdapter] Token 定时刷新成功")
            self._retry_count = 0
            self.loggedinChanged.emit()
            self.userInfoChanged.emit()
            self.tokenRefreshed.emit()
            self._start_refresh_timer()
        else:
            self._retry_count += 1
            if self._retry_count <= self.MAX_RETRY:
                log_warning(
                    f"[AuthAdapter] Token 刷新失败，{self._retry_count}/{self.MAX_RETRY}，"
                    f"{self.RETRY_INTERVAL_MS // 1000}s 后重试"
                )
                self._refresh_timer.start(self.RETRY_INTERVAL_MS)
            else:
                log_warning("[AuthAdapter] Token 刷新重试已达上限，停止重试")
                self.tokenExpired.emit()

    @Slot()
    def check_token_status(self) -> None:
        """应用从后台恢复时调用，检查 token 剩余时间。"""
        if not self._auth_service.is_logged_in:
            return

        remaining = self._auth_service.token_remaining_seconds
        if remaining <= self.REFRESH_AHEAD_SECONDS:
            log_info(
                f"[AuthAdapter] 后台恢复检查：剩余 {remaining}s，立即刷新"
            )
            self._refresh_timer.stop()
            self._on_refresh_timer()
        elif not self._refresh_timer.isActive():
            log_info("[AuthAdapter] 后台恢复检查：重启定时器")
            self._start_refresh_timer()
