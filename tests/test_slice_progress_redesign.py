"""Unit tests for slice progress redesign — resume slice computation.

Test that _compute_resume_slice returns the first unpassed slice.
"""

from src.backend.presentation.bridge import Bridge


class TestComputeResumeSlice:
    def test_first_unpassed_sequential(self):
        assert Bridge._compute_resume_slice([1, 1, 0, 0], 1, 1) == 3

    def test_all_passed_fallback(self):
        assert Bridge._compute_resume_slice([2, 2, 2], 1, 5) == 5

    def test_all_zero(self):
        assert Bridge._compute_resume_slice([0, 0, 0], 1, 1) == 1

    def test_partial_pass_count_min_3(self):
        assert Bridge._compute_resume_slice([3, 2, 0], 3, 1) == 2

    def test_first_slice_not_passed(self):
        assert Bridge._compute_resume_slice([0, 1, 1], 1, 1) == 1

    def test_empty_pass_counts_returns_fallback(self):
        assert Bridge._compute_resume_slice([], 1, 3) == 3

    def test_random_jump_doesnt_affect(self):
        assert Bridge._compute_resume_slice([1, 1, 0, 0, 0, 1, 0], 1, 1) == 3


class TestResumeSliceIntegration:
    """Verify random slice jumps don't corrupt the restore point."""

    def test_random_jump_preserves_resume(self):
        pass_counts = [1, 1, 1] + [0] * 47
        resume = Bridge._compute_resume_slice(pass_counts, 1, 37)
        assert resume == 4

    def test_resume_from_middle_after_random(self):
        pass_counts = [1] + [0] * 18 + [1] + [0] * 30
        resume = Bridge._compute_resume_slice(pass_counts, 1, 21)
        assert resume == 2

    def test_all_passed_full_cycle(self):
        pass_counts = [1] * 50
        resume = Bridge._compute_resume_slice(pass_counts, 1, 22)
        assert resume == 22
