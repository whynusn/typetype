# 分片进度恢复点重新设计 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restore point after random slice jump should be "first unpassed slice" instead of "last viewed slice"

**Architecture:** Add `_compute_resume_slice()` helper; change 3 Python restore sites to use it; update QML dialog to show both resume and current position. No JSON schema change, no new fields persisted.

**Tech Stack:** Python 3.12, PySide6/QML

---

### File Map

| File | Change |
|------|--------|
| `src/backend/presentation/bridge.py` | +`_compute_resume_slice()` helper; 3 restore sites use it; `getSliceProgressInfo` includes `resume_slice` |
| `src/qml/typing/SliceProgressRestoreDialog.qml` | Show `resume_slice` as primary, `saved_slice` (current) as secondary |
| `tests/` | Unit test for helper; integration test for random-jump behavior |

---

### Task 1: Add `_compute_resume_slice` helper

**Files:**
- Modify: `src/backend/presentation/bridge.py` (before `_find_progress`, around line 1820)

**Logic:** Returns the first 1-based slice index where `pass_counts[i] < pass_count_min`. If all slices meet the threshold, return `fallback`.

```python
@staticmethod
def _compute_resume_slice(
    pass_counts: list[int],
    pass_count_min: int,
    fallback: int,
) -> int:
    """返回第一个未达标的切片索引（1-based）。全部达标时回退到 fallback。"""
    for i, count in enumerate(pass_counts, start=1):
        if count < pass_count_min:
            return i
    return fallback
```

- [ ] **Write the code** — insert before `_find_progress` definition (~line 1820)
- [ ] **Verify syntax** — `uv run python -c "from src.backend.presentation.bridge import Bridge; print('ok')"`

---

### Task 2: Change setupLocalArticle restore point

**Files:**
- Modify: `src/backend/presentation/bridge.py` line 1146

**Before:**
```python
saved_slice = self._pending_restored_progress.get("current_slice", 1)
```

**After:**
```python
saved_slice = self._compute_resume_slice(
    self._pending_restored_progress.get("slice_pass_counts", []),
    self._pending_restored_progress.get("metrics", {}).get("pass_count_min", 1),
    self._pending_restored_progress.get("current_slice", 1),
)
```

- [ ] **Make the edit**
- [ ] **Verify:** Read the surrounding 5 lines to ensure alignment is correct

---

### Task 3: Change loadTrainerSegment restore point

**Files:**
- Modify: `src/backend/presentation/bridge.py` line 1273

Same change as Task 2.

**Before:**
```python
saved_slice = self._pending_restored_progress.get("current_slice", 1)
```

**After:**
```python
saved_slice = self._compute_resume_slice(
    self._pending_restored_progress.get("slice_pass_counts", []),
    self._pending_restored_progress.get("metrics", {}).get("pass_count_min", 1),
    self._pending_restored_progress.get("current_slice", 1),
)
```

- [ ] **Make the edit**

---

### Task 4: Change _apply_slice_setup restore point

**Files:**
- Modify: `src/backend/presentation/bridge.py` line 1554

**Before:**
```python
saved_slice = restored_progress.get("current_slice", 1)
```

**After:**
```python
saved_slice = Bridge._compute_resume_slice(
    restored_progress.get("slice_pass_counts", []),
    (restored_progress.get("metrics", {}) or {}).get("pass_count_min", 1),
    restored_progress.get("current_slice", 1),
)
```

Note: This is a static method call since `_apply_slice_setup` is not on `self` — actually it IS a regular method, so call `self._compute_resume_slice(...)`.

- [ ] **Make the edit**

---

### Task 5: Add `resume_slice` to `getSliceProgressInfo`

**Files:**
- Modify: `src/backend/presentation/bridge.py` lines 1883-1903

**Change:** Add `resume_slice` to the info dict.

```python
metrics = progress.get("metrics", {})
pass_counts = progress.get("slice_pass_counts", [])
pass_count_min = metrics.get("pass_count_min", 1)
saved_slice_idx = progress.get("current_slice", 1) - 1
info = {
    "saved_slice": progress.get("current_slice", 1),
    "resume_slice": self._compute_resume_slice(
        pass_counts, pass_count_min,
        progress.get("current_slice", 1),
    ),
    ...
}
```

- [ ] **Make the edit**

---

### Task 6: Update QML dialog

**Files:**
- Modify: `src/qml/typing/SliceProgressRestoreDialog.qml`

**Before:** Shows `root.progressInfo.saved_slice` for "分段进度".

**After (minimal):** Change `saved_slice` display to use `resume_slice`, and add a secondary line showing `saved_slice` (current position) when they differ.

In `SliceProgressRestoreDialog.qml`:
```qml
// Change line 63 to show resume_slice:
Text {
    typography: Typography.Caption
    text: qsTr("恢复点: 第 %1 / %2 段")
        .arg(root.progressInfo.resume_slice || root.progressInfo.saved_slice || 0)
        .arg(root.progressInfo.saved_total || 0)
}

// Add secondary line for current position (only if different):
Text {
    visible: root.progressInfo.resume_slice && root.progressInfo.resume_slice !== root.progressInfo.saved_slice
    typography: Typography.Caption
    color: Theme.currentTheme.colors.textSecondaryColor
    text: qsTr("(当前浏览: 第 %1 段)").arg(root.progressInfo.saved_slice || 0)
}
```

- [ ] **Make the edit**
- [ ] **Verify** — `uv run python main.py` launches without QML binding errors

---

### Task 7: Unit test for `_compute_resume_slice`

**Files:**
- Create: `tests/test_slice_progress_redesign.py`

- [ ] **Write failing test:**

```python
"""Unit tests for slice progress redesign — resume slice computation."""

import pytest
from src.backend.presentation.bridge import Bridge


class TestComputeResumeSlice:
    def test_first_unpassed_sequential(self):
        """pass_counts=[1,1,0,0], pass_count_min=1 → resume=3"""
        result = Bridge._compute_resume_slice([1, 1, 0, 0], 1, 1)
        assert result == 3

    def test_all_passed_fallback(self):
        """pass_counts=[2,2,2], pass_count_min=1 → fallback"""
        result = Bridge._compute_resume_slice([2, 2, 2], 1, 5)
        assert result == 5

    def test_all_zero(self):
        """pass_counts=[0,0,0], pass_count_min=1 → resume=1"""
        result = Bridge._compute_resume_slice([0, 0, 0], 1, 1)
        assert result == 1

    def test_partial_pass_count_min_3(self):
        """pass_counts=[3,2,0], pass_count_min=3 → resume=2 (needs one more)"""
        result = Bridge._compute_resume_slice([3, 2, 0], 3, 1)
        assert result == 2

    def test_first_slice_not_passed(self):
        """pass_counts=[0,1,1], pass_count_min=1 → resume=1"""
        result = Bridge._compute_resume_slice([0, 1, 1], 1, 1)
        assert result == 1

    def test_empty_pass_counts_returns_fallback(self):
        """pass_counts=[], pass_count_min=1 → fallback=3"""
        result = Bridge._compute_resume_slice([], 1, 3)
        assert result == 3

    def test_random_jump_doesnt_affect(self):
        """pass_counts=[1,1,0,0,0,1,0], pass_count_min=1 → resume=3 (not 6)"""
        result = Bridge._compute_resume_slice([1, 1, 0, 0, 0, 1, 0], 1, 1)
        assert result == 3
```

- [ ] **Run to see RED:**
```bash
uv run pytest tests/test_slice_progress_redesign.py -v
```
Expected: ALL PASS (the method already exists after Task 1)

- [ ] **Commit:**
```bash
git add tests/test_slice_progress_redesign.py
git commit -m "test: add unit tests for _compute_resume_slice"
```

---

### Task 8: Integration test — random jump doesn't overwrite resume

**Files:**
- Modify: `tests/test_slice_progress_redesign.py` (append)

- [ ] **Write the test:**

```python
class TestResumeSliceIntegration:
    """Verify that random slice jumps don't corrupt the restore point.
    
    These tests apply the same logic used in the restore code paths
    to verify the resume_slice computation matches design spec behavior.
    """

    def test_random_jump_preserves_resume(self):
        """Simulate: slices 1-3 passed, random jump to 37, saved progress.
        Resume slice should still be 4, not 37 (current_slice)."""
        pass_counts = [1, 1, 1] + [0] * 47
        pass_count_min = 1
        current_slice = 37  # after random jump
        
        resume = Bridge._compute_resume_slice(pass_counts, pass_count_min, current_slice)
        assert resume == 4, f"Expected 4 (first unpassed), got {resume}"

    def test_resume_from_middle_after_random(self):
        """Simulate: passed 1, random to 20 and passed it, then save.
        Resume should be 2 (first unpassed of sequential run)."""
        pass_counts = [1] + [0] * 18 + [1] + [0] * 30
        pass_count_min = 1
        current_slice = 21
        
        resume = Bridge._compute_resume_slice(pass_counts, pass_count_min, current_slice)
        assert resume == 2

    def test_all_passed_full_cycle(self):
        """All 50 slices passed, currently at slice 22.
        Resume should be 22 (fallback = current_slice)."""
        pass_counts = [1] * 50
        pass_count_min = 1
        current_slice = 22
        
        resume = Bridge._compute_resume_slice(pass_counts, pass_count_min, current_slice)
        assert resume == 22
```

- [ ] **Run to verify:**
```bash
uv run pytest tests/test_slice_progress_redesign.py -v
```
Expected: ALL 10 tests PASS

---

### Task 9: Final verification

- [ ] **Full test suite:**
```bash
uv run pytest -v 2>&1 | tail -20
```
Expected: same pass count as before changes (516+ or new count)

- [ ] **LSP diagnostics:**
```bash
# Using the tool
lsp_diagnostics on changed files
```

- [ ] **Launch check:**
```bash
uv run python -c "from src.backend.presentation.bridge import Bridge; b=Bridge._compute_resume_slice([1,1,0],1,1); print(f'resume={b}')"
```
Expected: `resume=3`

---

### Rollback Plan

If any test fails:
1. `git diff src/backend/presentation/bridge.py` — check the 3 restore sites
2. Ensure `self._compute_resume_slice(...)` call matches the helper signature
3. Ensure the `pass_counts` arg is being read from the correct dict key (`"slice_pass_counts"`)
4. If QML crashes, check `resume_slice` is in the JSON info dict
