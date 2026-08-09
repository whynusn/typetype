from ..ports.token_store import TokenStore
from ..security.secure_storage import SecureStorage


class SecureTokenStore(TokenStore):
    """基于系统密钥环的 token 存储适配。

    支持按名存取任意秘密（key 即名字）：``save_token(name, value)`` /
    ``get_token(name)``。供 ott-script 凭据注入（ADR-011 Phase 5.4）使用：
    仅父进程调用 ``get_token`` 取值，随后经一次性 fd 传给沙箱子进程
    （pass_fds），值不进环境变量、不写入沙箱文件系统。
    """

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
