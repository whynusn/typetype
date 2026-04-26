from ..ports.token_store import TokenStore
from ..security.secure_storage import SecureStorage


class SecureTokenStore(TokenStore):
    """基于系统密钥环的 token 存储适配。"""

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}

    def get_token(self, key: str) -> str | None:
        if key not in self._cache:
            self._cache[key] = SecureStorage.get_jwt(key)
        return self._cache[key]

    def save_token(self, key: str, token: str) -> None:
        SecureStorage.save_jwt(key, token)
        self._cache[key] = token

    def delete_token(self, key: str) -> None:
        SecureStorage.delete_jwt(key)
        self._cache[key] = None
