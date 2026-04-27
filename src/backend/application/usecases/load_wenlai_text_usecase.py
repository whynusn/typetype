from dataclasses import dataclass

from ...models.dto.wenlai_dto import WenlaiDirection, WenlaiText
from ...ports.wenlai_provider import WenlaiAuthRequiredError
from ..gateways.wenlai_gateway import WenlaiGateway


@dataclass(frozen=True)
class WenlaiLoadResult:
    text: WenlaiText


class LoadWenlaiTextUseCase:
    """晴发文载文用例。"""

    def __init__(self, gateway: WenlaiGateway):
        self._gateway = gateway

    def _ensure_logged_in(self) -> None:
        if not self._gateway.is_logged_in():
            raise WenlaiAuthRequiredError("请先在设置页登录晴发文")

    def load_random(self) -> WenlaiLoadResult:
        self._ensure_logged_in()
        config = self._gateway.config
        text = self._gateway.fetch_random_text(
            difficulty_level=config.difficulty_level,
            length=config.length,
            strict_length=config.strict_length,
            category=config.category,
        )
        return WenlaiLoadResult(text=text)

    def load_adjacent(self, current: WenlaiText, direction: str) -> WenlaiLoadResult:
        self._ensure_logged_in()
        if direction not in {WenlaiDirection.NEXT.value, WenlaiDirection.PREV.value}:
            raise ValueError("direction must be 'next' or 'prev'")
        config = self._gateway.config
        is_next = direction == "next"
        text = self._gateway.fetch_adjacent_text(
            book_id=current.book_id,
            sort_num=current.sort_num,
            direction=direction,
            category=current.category or config.category,
            end_sort_num=current.end_sort_num if is_next else 0,
            end_chars=current.end_chars if is_next else "",
            start_chars=current.start_chars if not is_next else "",
            length=config.length,
            strict_length=config.strict_length,
        )
        return WenlaiLoadResult(text=text)
