from typing import Protocol


class TokenStore(Protocol):
    """JWT/token 持久化端口。"""

    def get_token(self, key: str) -> str | None: ...

    def save_token(self, key: str, token: str) -> None: ...

    def delete_token(self, key: str) -> None: ...
