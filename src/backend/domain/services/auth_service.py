import keyring

from ...application.ports.auth_provider import AuthProvider
from ...security.secure_storage import SecureStorage


class AuthService:
    """认证服务，纯业务逻辑，无 Qt 依赖。

    职责：
    - 用户登录认证（username/password 验证）
    - Token 管理（保存、刷新、验证）
    - 用户状态维护（current_user_id, current_nickname 等）

    不负责：
    - UI 交互（由 Bridge 负责）
    - 信号发射（由 Bridge 负责）
    """

    def __init__(
        self,
        auth_provider: AuthProvider,
        login_url: str,
        validate_url: str,
        refresh_url: str,
    ):
        self._auth_provider = auth_provider
        self._login_url = login_url
        self._validate_url = validate_url
        self._refresh_url = refresh_url
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
        """
        执行登录请求。

        返回:
            (success, message, user_data)
        """
        data = self._auth_provider.post_json(
            self._login_url,
            {"username": username, "password": password},
        )

        if data is None:
            error_msg = str(self._auth_provider.last_error or "网络请求失败")
            return False, error_msg, {}

        if data.get("code") != 200:
            return False, data.get("message", "登录失败"), {}

        user_data = data.get("data", {})
        access_token = user_data.get("accessToken")
        user_info = user_data.get("user", {})

        user_id = str(user_info.get("id", ""))
        nickname = user_info.get("nickname", "")

        SecureStorage.save_jwt("current_user", access_token)
        SecureStorage.save_jwt(
            "current_user_refresh", user_data.get("refreshToken", "")
        )

        self._current_user_id = user_id
        self._current_username = username
        self._current_nickname = nickname

        return True, "登录成功", user_info

    def logout(self):
        """执行登出。"""
        try:
            keyring.delete_password(SecureStorage.SERVICE_NAME, "jwt_current_user")
        except Exception:
            pass
        try:
            keyring.delete_password(
                SecureStorage.SERVICE_NAME, "jwt_current_user_refresh"
            )
        except Exception:
            pass

        self._current_user_id = ""
        self._current_username = ""
        self._current_nickname = ""

    def refresh_token(self) -> tuple[bool, dict]:
        """
        使用 refresh token 刷新 access token。

        返回:
            (success, user_data)
        """
        refresh_token = SecureStorage.get_jwt("current_user_refresh")
        if not refresh_token:
            return False, {}

        data = self._auth_provider.request(
            "POST",
            self._refresh_url,
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

        if data is None:
            return False, {}

        if data.get("code") != 200:
            return False, {}

        user_data = data.get("data", {})
        new_access_token = user_data.get("accessToken")
        new_refresh_token = user_data.get("refreshToken")

        SecureStorage.save_jwt("current_user", new_access_token)
        if new_refresh_token:
            SecureStorage.save_jwt("current_user_refresh", new_refresh_token)

        user_info = user_data.get("user", {})
        self._current_user_id = str(user_info.get("id", ""))
        self._current_username = user_info.get("username", "")
        self._current_nickname = user_info.get("nickname", "")

        return True, user_info

    def validate_token(self) -> tuple[bool, dict]:
        """
        验证当前 token 是否有效，失败则尝试刷新。

        返回:
            (is_valid, user_data)
        """
        jwt = SecureStorage.get_jwt("current_user")
        if not jwt:
            return False, {}

        data = self._auth_provider.request(
            "GET",
            self._validate_url,
            headers={"Authorization": f"Bearer {jwt}"},
        )

        if data and data.get("code") == 200:
            user_data = data.get("data", {})
            self._current_user_id = str(user_data.get("id", ""))
            self._current_username = user_data.get("username", "")
            self._current_nickname = user_data.get("nickname", "")
            return True, user_data

        return self.refresh_token()

    def initialize(self) -> bool:
        """
        初始化时验证 token。

        返回:
            是否已登录
        """
        is_valid, user_data = self.validate_token()
        return is_valid
