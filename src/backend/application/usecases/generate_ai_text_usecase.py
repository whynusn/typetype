"""AI 智能推荐文本生成用例。"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...integration.llm_text_provider import LlmTextProvider
    from ...integration.sqlite_char_stats_repository import SqliteCharStatsRepository


@dataclass(frozen=True)
class AiTextResult:
    success: bool
    text: str = ""
    title: str = ""
    error_message: str = ""


class GenerateAiTextUseCase:
    """根据用户薄弱字调用 LLM 生成针对性练习文本。"""

    def __init__(
        self,
        llm_provider: "LlmTextProvider",
        char_stats_repo: "SqliteCharStatsRepository",
    ) -> None:
        self._llm = llm_provider
        self._char_stats_repo = char_stats_repo

    def execute(self, weak_char_limit: int = 20) -> AiTextResult:
        """生成 AI 推荐文本。"""
        weak_chars = self._get_weak_chars(weak_char_limit)
        if not weak_chars:
            return AiTextResult(
                success=False,
                error_message="没有足够的打字数据，请先练习一些文本",
            )
        text = self._llm.generate_text(weak_chars)
        return AiTextResult(success=True, text=text, title="AI 智能推荐")

    def _get_weak_chars(self, limit: int) -> list[str]:
        stats = self._char_stats_repo.get_chars_by_sort(sort_mode="error_rate", n=limit)
        return [s.char for s in stats]
