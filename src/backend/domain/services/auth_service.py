import base64
import json
import time

import keyring

from ...ports.auth_provider import AuthProvider
from ...security.secure_storage import SecureStorage
from ...utils.logger import log_warning


def _decode_jwt_exp(token: str) -> int | None:
    """从 JWT 中解码 exp 声明（Unix 时间戳）。"""
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("exp")
    except (IndexError, json.JSONDecodeError, ValueError):
        return None


class AuthService:
    """认证服务，纯业务逻辑，无 Qt 依赖。"""

    REFRESH_AHEAD_SECONDS = 120

    def __init__(self, auth_provider: AuthProvider):
        self._auth_provider = auth_provider
        self._current_user_id = ""
        self._current_username = ""
        self._current_nickname = ""
        self._expires_in: int = 0
        self._token_issued_at: float = 0.0

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

    @property
    def refresh_interval_seconds(self) -> int:
        """计算刷新间隔（秒），至少 60 秒。"""
        if self._expires_in <= 0:
            return 0
        return max(self._expires_in - self.REFRESH_AHEAD_SECONDS, 60)

    @property
    def token_remaining_seconds(self) -> int:
        """计算 token 剩余有效秒数。"""
        if self._expires_in <= 0 or self._token_issued_at <= 0:
            return 0
        elapsed = time.monotonic() - self._token_issued_at
        return max(int(self._expires_in - elapsed), 0)

    # === 流程方法 ===

    def _apply_jwt_exp(self, token: str) -> None:
        """从 JWT 的 exp 声明设置 _expires_in / _token_issued_at。"""
        exp = _decode_jwt_exp(token)
        if exp:
            self._expires_in = max(int(exp - time.time()), 0)
            self._token_issued_at = time.monotonic()

    def login(self, username: str, password: str) -> tuple[bool, str, dict]:
        result = self._auth_provider.login(username, password)
        if not result.success:
            return False, result.error_message, {}

        SecureStorage.save_jwt("current_user", result.access_token)
        SecureStorage.save_jwt("current_user_refresh", result.refresh_token)

        self._token_issued_at = time.monotonic()
        if result.expires_in > 0:
            self._expires_in = result.expires_in
        else:
            self._apply_jwt_exp(result.access_token)

        user_info = result.user_info
        self._current_user_id = str(user_info.get("id", ""))
        self._current_username = username
        self._current_nickname = user_info.get("nickname", "")

        return True, "登录成功", user_info

    def register(
        self, username: str, password: str, nickname: str = ""
    ) -> tuple[bool, str, dict]:
        result = self._auth_provider.register(username, password, nickname)
        if not result.success:
            return False, result.error_message, {}

        return self.login(username, password)

    def logout(self):
        for key in ("current_user", "current_user_refresh"):
            try:
                keyring.delete_password(SecureStorage.SERVICE_NAME, f"jwt_{key}")
            except Exception as e:
                log_warning(f"登出时清除 {key} 失败: {e}")

        self._current_user_id = ""
        self._current_username = ""
        self._current_nickname = ""
        self._expires_in = 0
        self._token_issued_at = 0.0

    def refresh_token(self) -> tuple[bool, dict]:
        ref = SecureStorage.get_jwt("current_user_refresh")
        if not ref:
            return False, {}

        result = self._auth_provider.refresh_token(ref)
        if not result.success:
            return False, {}

        SecureStorage.save_jwt("current_user", result.access_token)
        if result.refresh_token:
            SecureStorage.save_jwt("current_user_refresh", result.refresh_token)

        self._token_issued_at = time.monotonic()
        if result.expires_in > 0:
            self._expires_in = result.expires_in
        else:
            self._apply_jwt_exp(result.access_token)

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
        # validate_token 的 /api/v1/users/me 不返回 expires_in，
        # 直接从 JWT 的 exp 声明本地解码，无需额外网络请求。
        if is_valid and self._expires_in <= 0:
            jwt = SecureStorage.get_jwt("current_user")
            if jwt:
                self._apply_jwt_exp(jwt)
        return is_valid
