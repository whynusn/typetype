from typing import Protocol

from ..models.dto.wenlai_dto import (
    WenlaiCategory,
    WenlaiDifficulty,
    WenlaiLoginResult,
    WenlaiText,
)


class WenlaiAuthRequiredError(Exception):
    """晴发文认证缺失或已过期。"""


class WenlaiServiceError(Exception):
    """晴发文服务业务错误。"""


class WenlaiProvider(Protocol):
    """晴发文服务端能力端口。"""

    def update_base_url(self, base_url: str) -> None: ...

    def login(self, username: str, password: str) -> WenlaiLoginResult: ...

    def fetch_random_text(
        self,
        *,
        difficulty_level: int,
        length: int,
        strict_length: bool,
        category: str,
    ) -> WenlaiText: ...

    def fetch_adjacent_text(
        self,
        *,
        book_id: int,
        sort_num: int,
        direction: str,
        category: str,
        end_sort_num: int,
        end_chars: str,
        start_chars: str,
        length: int,
        strict_length: bool,
    ) -> WenlaiText: ...

    def get_difficulties(self) -> list[WenlaiDifficulty]: ...

    def get_categories(self) -> list[WenlaiCategory]: ...
