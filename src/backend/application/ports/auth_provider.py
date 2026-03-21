from typing import Any, Protocol


class AuthProvider(Protocol):
    @property
    def last_error(self) -> Exception | None: ...

    def post_json(self, url: str, payload: dict[Any, Any]) -> dict[str, Any] | None: ...

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None: ...
