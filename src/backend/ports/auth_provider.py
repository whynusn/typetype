from typing import Protocol

from ..models.dto.auth_dto import AuthResult


class AuthProvider(Protocol):
    """认证协议，封装登录、token 验证与刷新。"""

    def login(self, username: str, password: str) -> AuthResult: ...

    def register(
        self, username: str, password: str, nickname: str = ""
    ) -> AuthResult: ...

    def validate_token(self, token: str) -> AuthResult: ...

    def refresh_token(self, refresh_token: str) -> AuthResult: ...
