from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from ...models.dto.text_session import SegmentResult, TextHandle
from ...ports.text_segment_provider import TextSegmentProvider

if TYPE_CHECKING:
    pass

_FULL_SHUFFLE_THRESHOLD = 1_000_000  # 1MB 以下全量 shuffle，以上用虚拟 permutation


class _FeistelPermutation:
    """基于平衡 Feistel 网络的可逆伪随机排列。

    对 [0, range) 内的整数建立双射映射，只需 O(1) 内存。
    使用平衡 Feistel（等宽左右半部分）+ cycle walking 确保输出在 [0, range) 内。
    F 函数使用 SHA-256 混淆，保证 cycle walking 快速收敛（期望 2 轮以内）。
    """

    _ROUNDS = 8

    def __init__(self, range_: int, seed: int) -> None:
        self._range = range_
        total_bits = max(2, (range_ - 1).bit_length() + 1)
        if total_bits % 2:
            total_bits += 1
        self._half_bits = total_bits // 2
        self._half_mask = (1 << self._half_bits) - 1
        self._domain = 1 << total_bits
        self._round_keys = self._derive_round_keys(seed)

    @staticmethod
    def _derive_round_keys(seed: int) -> list[int]:
        keys = []
        current = seed
        for _ in range(_FeistelPermutation._ROUNDS):
            h = hashlib.sha256(current.to_bytes(32, "big"))
            current = int.from_bytes(h.digest(), "big")
            keys.append(current)
        return keys

    def _F(self, value: int, round_key: int) -> int:
        data = (value ^ round_key).to_bytes(32, "big")
        h = hashlib.sha256(data).digest()
        return int.from_bytes(h[:8], "big") & self._half_mask

    def _feistel(self, value: int) -> int:
        left = value >> self._half_bits
        right = value & self._half_mask
        for rk in self._round_keys:
            left, right = right, (left ^ self._F(right, rk)) & self._half_mask
        return (left << self._half_bits) | right

    def encode(self, index: int) -> int:
        if self._range <= 1:
            return index
        result = self._feistel(index)
        while result >= self._range:
            result = self._feistel(result)
        return result


class _ShuffledSegmentProvider:
    """通过虚拟 permutation 从原始 provider 逐字符构造乱序段。"""

    def __init__(self, original: TextSegmentProvider, perm: _FeistelPermutation) -> None:
        self._original = original
        self._perm = perm

    def get_segment(self, start: int, length: int) -> str:
        if start < 0 or length <= 0:
            return ""
        total = self._original.get_total_chars()
        if start >= total:
            return ""
        actual_length = min(length, total - start)
        indices = [self._perm.encode(start + i) for i in range(actual_length)]
        sorted_pairs = sorted(enumerate(indices), key=lambda p: p[1])
        result = [""] * actual_length
        for dest_idx, orig_idx in sorted_pairs:
            result[dest_idx] = self._original.get_segment(orig_idx, 1)
        return "".join(result)

    def get_total_chars(self) -> int:
        return self._original.get_total_chars()


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

    def shuffle_all_virtual(self, seed: int) -> "TextSessionUseCase":
        """全文虚拟乱序：小文本全量 shuffle，大文本用 Feistel permutation。

        返回新的 TextSessionUseCase，后续分片操作在乱序后的序列上进行。
        """
        if self._total_chars <= 0:
            return self

        if self._total_chars <= _FULL_SHUFFLE_THRESHOLD:
            return self._shuffle_full(seed)

        return self._shuffle_feistel(seed)

    def _shuffle_full(self, seed: int) -> "TextSessionUseCase":
        """小文本：全量读入内存 shuffle，创建新的 InMemory provider。"""
        from ...integration.in_memory_segment_provider import InMemorySegmentProvider

        text = self._provider.get_segment(0, self._total_chars)
        chars = list(text)
        import random

        rng = random.Random(seed)
        rng.shuffle(chars)
        shuffled = "".join(chars)
        new_provider = InMemorySegmentProvider(shuffled)
        new_handle = TextHandle(
            kind=self._handle.kind,
            identifier=self._handle.identifier,
            title=self._handle.title,
            char_count=len(shuffled),
            version=self._handle.version,
            source_key=self._handle.source_key,
            server_text_id=self._handle.server_text_id,
        )
        return TextSessionUseCase(new_provider, new_handle)

    def _shuffle_feistel(self, seed: int) -> "TextSessionUseCase":
        """大文本：用 Feistel permutation 做虚拟乱序。"""
        perm = _FeistelPermutation(self._total_chars, seed)
        new_provider = _ShuffledSegmentProvider(self._provider, perm)
        new_handle = TextHandle(
            kind=self._handle.kind,
            identifier=self._handle.identifier,
            title=self._handle.title,
            char_count=self._total_chars,
            version=self._handle.version,
            source_key=self._handle.source_key,
            server_text_id=self._handle.server_text_id,
        )
        return TextSessionUseCase(new_provider, new_handle)
