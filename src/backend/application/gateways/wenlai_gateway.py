from ...config.runtime_config import RuntimeConfig, WenlaiConfig
from ...models.dto.wenlai_dto import (
    WenlaiCategory,
    WenlaiDifficulty,
    WenlaiLoginResult,
    WenlaiText,
)
from ...ports.token_store import TokenStore
from ...ports.wenlai_provider import WenlaiProvider
from ...utils.logger import log_warning


class WenlaiGateway:
    """晴发文应用层网关。"""

    TOKEN_KEY = "wenlai_user"

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        provider: WenlaiProvider,
        token_store: TokenStore,
    ) -> None:
        self._runtime_config = runtime_config
        self._provider = provider
        self._token_store = token_store

    @property
    def config(self) -> WenlaiConfig:
        return self._runtime_config.wenlai

    def is_logged_in(self) -> bool:
        return bool(
            self._token_store.get_token(self.TOKEN_KEY) and self.config.username
        )

    def login(self, username: str, password: str) -> WenlaiLoginResult:
        result = self._provider.login(username, password)
        self._token_store.save_token(self.TOKEN_KEY, result.token)
        self._runtime_config.update_wenlai_user(
            username=result.username,
            display_name=result.display_name,
            user_id=result.user_id,
        )
        return result

    def logout(self) -> None:
        try:
            self._token_store.delete_token(self.TOKEN_KEY)
        except Exception as e:
            log_warning(f"退出晴发文登录时清除 token 失败: {e}")
        self._runtime_config.clear_wenlai_user()

    def update_config(
        self,
        *,
        base_url: str | None = None,
        length: int | None = None,
        difficulty_level: int | None = None,
        category: str | None = None,
        segment_mode: str | None = None,
        strict_length: bool | None = None,
    ) -> None:
        self._runtime_config.update_wenlai_config(
            base_url=base_url,
            length=length,
            difficulty_level=difficulty_level,
            category=category,
            segment_mode=segment_mode,
            strict_length=strict_length,
        )
        self._provider.update_base_url(self.config.base_url)

    def fetch_random_text(
        self,
        *,
        difficulty_level: int,
        length: int,
        strict_length: bool,
        category: str,
    ) -> WenlaiText:
        return self._provider.fetch_random_text(
            difficulty_level=difficulty_level,
            length=length,
            strict_length=strict_length,
            category=category,
        )

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
    ) -> WenlaiText:
        return self._provider.fetch_adjacent_text(
            book_id=book_id,
            sort_num=sort_num,
            direction=direction,
            category=category,
            end_sort_num=end_sort_num,
            end_chars=end_chars,
            start_chars=start_chars,
            length=length,
            strict_length=strict_length,
        )

    def get_difficulties(self) -> list[WenlaiDifficulty]:
        return self._provider.get_difficulties()

    def get_categories(self) -> list[WenlaiCategory]:
        return self._provider.get_categories()
