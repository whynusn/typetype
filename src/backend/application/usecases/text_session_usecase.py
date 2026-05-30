from __future__ import annotations

from ...models.dto.text_session import SegmentResult, TextHandle
from ...ports.text_segment_provider import TextSegmentProvider


class TextSessionUseCase:
    """统一载文会话业务编排。

    所有来源共享同一套逻辑：分片、导航、乱序、进度。
    差异仅在于 provider 的数据获取方式。
    """

    def __init__(self, provider: TextSegmentProvider, handle: TextHandle) -> None:
        self._provider = provider
        self._handle = handle
        self._total_chars = provider.get_total_chars()

    @property
    def handle(self) -> TextHandle:
        return self._handle

    @property
    def total_chars(self) -> int:
        return self._total_chars

    def get_segment(self, index: int, slice_size: int) -> SegmentResult:
        """按 1-based 段索引取段内容。"""
        total = max(1, (self._total_chars + slice_size - 1) // slice_size)
        clamped = max(1, min(index, total))
        start = (clamped - 1) * slice_size
        content = self._provider.get_segment(start, slice_size)
        return SegmentResult(content=content, index=clamped, total=total)

    def shuffle_segment(self, content: str, seed: int | None = None) -> str:
        """对给定文本做局部乱序。"""
        import random

        if not content:
            return ""
        chars = list(content)
        rng = random.Random(seed) if seed is not None else random.Random()
        rng.shuffle(chars)
        return "".join(chars)
