import keyring

from ...application.ports.auth_provider import AuthProvider
from ...security.secure_storage import SecureStorage
from ...utils.logger import log_warning


class AuthService:
    """认证服务，纯业务逻辑，无 Qt 依赖。"""

    def __init__(self, auth_provider: AuthProvider):
        self._auth_provider = auth_provider
        self._current_user_id = ""
        self._current_username = ""
        self._current_nickname = ""

    @property
    def is_logged_in(self) -> bool:
        return bool(self._current_user_id)

    @property
    def current_user_id(self) -> str:
        return self._current_user_id

    @property
    def current_username(self) -> str:
        return self._current_username

    @property
    def current_nickname(self) -> str:
        return self._current_nickname

    def login(self, username: str, password: str) -> tuple[bool, str, dict]:
        result = self._auth_provider.login(username, password)
        if not result.success:
            return False, result.error_message, {}

        SecureStorage.save_jwt("current_user", result.access_token)
        SecureStorage.save_jwt("current_user_refresh", result.refresh_token)

        user_info = result.user_info
        self._current_user_id = str(user_info.get("id", ""))
        self._current_username = username
        self._current_nickname = user_info.get("nickname", "")

        return True, "登录成功", user_info

    def logout(self):
        try:
            keyring.delete_password(SecureStorage.SERVICE_NAME, "jwt_current_user")
        except Exception as e:
            log_warning(f"登出时清除 token 失败: {e}")
        try:
            keyring.delete_password(
                SecureStorage.SERVICE_NAME, "jwt_current_user_refresh"
            )
        except Exception as e:
            log_warning(f"登出时清除 refresh token 失败: {e}")

        self._current_user_id = ""
        self._current_username = ""
        self._current_nickname = ""

    def refresh_token(self) -> tuple[bool, dict]:
        refresh_token = SecureStorage.get_jwt("current_user_refresh")
        if not refresh_token:
            return False, {}

        result = self._auth_provider.refresh_token(refresh_token)
        if not result.success:
            return False, {}

        SecureStorage.save_jwt("current_user", result.access_token)
        if result.refresh_token:
            SecureStorage.save_jwt("current_user_refresh", result.refresh_token)

        user_info = result.user_info
        self._current_user_id = str(user_info.get("id", ""))
        self._current_username = user_info.get("username", "")
        self._current_nickname = user_info.get("nickname", "")

        return True, user_info

    def validate_token(self) -> tuple[bool, dict]:
        jwt = SecureStorage.get_jwt("current_user")
        if not jwt:
            return False, {}

        result = self._auth_provider.validate_token(jwt)
        if result.success:
            user_info = result.user_info
            self._current_user_id = str(user_info.get("id", ""))
            self._current_username = user_info.get("username", "")
            self._current_nickname = user_info.get("nickname", "")
            return True, user_info

        return self.refresh_token()

    def initialize(self) -> bool:
        is_valid, _ = self.validate_token()
        return is_valid
