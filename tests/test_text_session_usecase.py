"""TextSessionUseCase 和 Feistel permutation 测试。"""

from src.backend.application.usecases.text_session_usecase import (
    TextSessionUseCase,
    _FeistelPermutation,
    _ShuffledSegmentProvider,
)
from src.backend.integration.in_memory_segment_provider import InMemorySegmentProvider
from src.backend.models.dto.text_session import TextHandle, TextKind


def _make_handle(char_count: int = 0) -> TextHandle:
    return TextHandle(
        kind=TextKind.LOCAL_ARTICLE,
        identifier="test-id",
        title="Test",
        char_count=char_count,
        version="1",
    )


def _make_usecase(text: str) -> TextSessionUseCase:
    provider = InMemorySegmentProvider(text)
    handle = _make_handle(len(text))
    return TextSessionUseCase(provider, handle)


class TestFeistelPermutation:
    def test_bijection_various_ranges(self):
        for n in [3, 7, 13, 97, 100, 127, 128, 129, 1000, 12345]:
            perm = _FeistelPermutation(n, seed=42)
            results = [perm.encode(i) for i in range(n)]
            assert sorted(results) == list(range(n)), f"Failed for n={n}"

    def test_different_seeds_give_different_permutations(self):
        n = 100
        perm1 = _FeistelPermutation(n, seed=1)
        perm2 = _FeistelPermutation(n, seed=2)
        results1 = [perm1.encode(i) for i in range(n)]
        results2 = [perm2.encode(i) for i in range(n)]
        assert results1 != results2

    def test_same_seed_gives_same_permutation(self):
        n = 100
        perm1 = _FeistelPermutation(n, seed=42)
        perm2 = _FeistelPermutation(n, seed=42)
        for i in range(n):
            assert perm1.encode(i) == perm2.encode(i)

    def test_single_element(self):
        perm = _FeistelPermutation(1, seed=42)
        assert perm.encode(0) == 0

    def test_two_elements(self):
        perm = _FeistelPermutation(2, seed=42)
        results = [perm.encode(i) for i in range(2)]
        assert sorted(results) == [0, 1]


class TestShuffledSegmentProvider:
    def test_preserves_all_characters(self):
        text = "Hello, World! 你好世界"
        provider = InMemorySegmentProvider(text)
        perm = _FeistelPermutation(len(text), seed=42)
        shuffled = _ShuffledSegmentProvider(provider, perm)
        result = shuffled.get_segment(0, len(text))
        assert sorted(result) == sorted(text)

    def test_length_preserved(self):
        text = "abcdef"
        provider = InMemorySegmentProvider(text)
        perm = _FeistelPermutation(len(text), seed=42)
        shuffled = _ShuffledSegmentProvider(provider, perm)
        for start in range(len(text)):
            for length in range(1, len(text) - start + 1):
                result = shuffled.get_segment(start, length)
                assert len(result) == length

    def test_empty_segment(self):
        provider = InMemorySegmentProvider("abc")
        perm = _FeistelPermutation(3, seed=1)
        shuffled = _ShuffledSegmentProvider(provider, perm)
        assert shuffled.get_segment(0, 0) == ""
        assert shuffled.get_segment(-1, 5) == ""

    def test_get_total_chars(self):
        text = "abcdef"
        provider = InMemorySegmentProvider(text)
        perm = _FeistelPermutation(len(text), seed=42)
        shuffled = _ShuffledSegmentProvider(provider, perm)
        assert shuffled.get_total_chars() == len(text)


class TestShuffleAllVirtual:
    def test_small_text_full_shuffle(self):
        text = "Hello"
        usecase = _make_usecase(text)
        shuffled = usecase.shuffle_all_virtual(seed=42)
        result = shuffled.get_segment(1, len(text))
        assert sorted(result.content) == sorted(text)

    def test_returns_new_usecase(self):
        usecase = _make_usecase("abc")
        shuffled = usecase.shuffle_all_virtual(seed=1)
        assert shuffled is not usecase

    def test_empty_text(self):
        usecase = _make_usecase("")
        shuffled = usecase.shuffle_all_virtual(seed=1)
        assert shuffled is usecase

    def test_deterministic_with_seed(self):
        text = "Hello, World!"
        usecase1 = _make_usecase(text)
        usecase2 = _make_usecase(text)
        r1 = usecase1.shuffle_all_virtual(seed=42).get_segment(1, len(text))
        r2 = usecase2.shuffle_all_virtual(seed=42).get_segment(1, len(text))
        assert r1.content == r2.content

    def test_feistel_path_preserves_characters(self):
        import src.backend.application.usecases.text_session_usecase as mod

        text = "ABC" * 100  # 300 chars
        usecase = _make_usecase(text)
        orig_threshold = mod._FULL_SHUFFLE_THRESHOLD
        mod._FULL_SHUFFLE_THRESHOLD = 100  # force feistel
        try:
            shuffled = usecase.shuffle_all_virtual(seed=42)
            result = shuffled.get_segment(1, 50)
            assert len(result.content) == 50
            # Characters should come from the original text
            for ch in result.content:
                assert ch in text
        finally:
            mod._FULL_SHUFFLE_THRESHOLD = orig_threshold

    def test_feistel_path_all_segments_cover_all_chars(self):
        import src.backend.application.usecases.text_session_usecase as mod

        text = "ABCDE" * 20  # 100 chars
        usecase = _make_usecase(text)
        orig_threshold = mod._FULL_SHUFFLE_THRESHOLD
        mod._FULL_SHUFFLE_THRESHOLD = 10  # force feistel
        try:
            shuffled = usecase.shuffle_all_virtual(seed=42)
            all_chars = ""
            for i in range(1, shuffled.total_chars + 1):
                seg = shuffled.get_segment(i, 1)
                all_chars += seg.content
            assert sorted(all_chars) == sorted(text)
        finally:
            mod._FULL_SHUFFLE_THRESHOLD = orig_threshold
