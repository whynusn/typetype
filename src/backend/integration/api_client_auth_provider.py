from typing import Any

from ..infrastructure.api_client import ApiClient
from ..models.dto.auth_dto import AuthResult


class ApiClientAuthProvider:
    """基于 ApiClient 的认证实现，封装 HTTP 细节。"""

    def __init__(
        self,
        api_client: ApiClient,
        login_url: str,
        validate_url: str,
        refresh_url: str,
        register_url: str = "",
    ):
        self._api_client = api_client
        self._login_url = login_url
        self._validate_url = validate_url
        self._refresh_url = refresh_url
        self._register_url = register_url

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 及其派生的 API URL。"""
        new_base_url = new_base_url.rstrip("/")
        self._login_url = f"{new_base_url}/api/v1/auth/login"
        self._validate_url = f"{new_base_url}/api/v1/users/me"
        self._refresh_url = f"{new_base_url}/api/v1/auth/refresh"
        self._register_url = f"{new_base_url}/api/v1/auth/register"

    def login(self, username: str, password: str) -> AuthResult:
        data = self._api_client.request(
            "POST",
            self._login_url,
            json={"username": username, "password": password},
        )
        return self._parse_auth_response(data)

    def register(self, username: str, password: str, nickname: str = "") -> AuthResult:
        payload: dict[str, Any] = {
            "username": username,
            "password": password,
            "confirmPassword": password,
        }
        if nickname:
            payload["nickname"] = nickname
        data = self._api_client.request(
            "POST",
            self._register_url,
            json=payload,
        )
        return self._parse_register_response(data)

    def validate_token(self, token: str) -> AuthResult:
        data = self._api_client.request(
            "GET",
            self._validate_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        return self._parse_user_response(data)

    def refresh_token(self, refresh_token: str) -> AuthResult:
        data = self._api_client.request(
            "POST",
            self._refresh_url,
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        return self._parse_auth_response(data)

    def _parse_auth_response(self, data: dict[str, Any] | None) -> AuthResult:
        """解析登录/刷新响应（含 token）。"""
        if data is None:
            return AuthResult(
                success=False,
                error_message=str(self._api_client.last_error or "网络请求失败"),
            )
        if data.get("code") != 200:
            return AuthResult(
                success=False,
                error_message=data.get("message", "请求失败"),
            )
        payload = data.get("data", {})
        return AuthResult(
            success=True,
            access_token=payload.get("accessToken", ""),
            refresh_token=payload.get("refreshToken", ""),
            expires_in=payload.get("expiresIn", 0),
            user_info=payload.get("user", {}),
        )

    def _parse_user_response(self, data: dict[str, Any] | None) -> AuthResult:
        """解析用户信息响应（不含 token）。"""
        if data is None:
            return AuthResult(success=False)
        if data.get("code") != 200:
            return AuthResult(success=False)
        return AuthResult(
            success=True,
            user_info=data.get("data", {}),
        )

    def _parse_register_response(self, data: dict[str, Any] | None) -> AuthResult:
        """解析注册响应（不含 token）。"""
        if data is None:
            return AuthResult(
                success=False,
                error_message=str(self._api_client.last_error or "网络请求失败"),
            )
        if data.get("code") != 200:
            return AuthResult(
                success=False,
                error_message=data.get("message", "注册失败"),
            )
        return AuthResult(
            success=True,
            user_info=data.get("data", {}),
        )
