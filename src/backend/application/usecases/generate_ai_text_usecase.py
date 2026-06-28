"""AI 智能推荐文本生成用例。"""

from collections.abc import Callable
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

    def execute(
        self,
        weak_char_limit: int = 20,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AiTextResult:
        """生成 AI 推荐文本。

        Args:
            on_chunk: 流式回调，每收到一块文本时调用。
        """
        weak_chars = self._get_weak_chars(weak_char_limit)
        if not weak_chars:
            return AiTextResult(
                success=False,
                error_message="没有足够的打字数据，请先练习一些文本",
            )

        chunks: list[str] = []
        for chunk in self._llm.generate_text_stream(weak_chars):
            chunks.append(chunk)
            if on_chunk:
                on_chunk(chunk)

        text = "".join(chunks)
        if not text.strip():
            return AiTextResult(
                success=False,
                error_message="AI 返回内容为空",
            )
        return AiTextResult(success=True, text=text, title="AI 智能推荐")

    def _get_weak_chars(self, limit: int) -> list[str]:
        import random

        # 优先取近 7 天的薄弱字，不足时回退到全历史
        stats = self._char_stats_repo.get_chars_by_sort(
            sort_mode="error_rate", n=limit * 3, recent_days=7
        )
        if len(stats) < limit:
            stats = self._char_stats_repo.get_chars_by_sort(
                sort_mode="error_rate", n=limit * 3
            )
        chars = [s.char for s in stats]
        random.shuffle(chars)
        return chars[:limit]
