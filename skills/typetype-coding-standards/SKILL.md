---
name: typetype-coding-standards
description: TypeType coding standards, naming conventions, Python/QML style rules, and common pitfalls. Use when writing new code or refactoring.
---

# TypeType Coding Standards

## Python

### Import Order

**One blank line between groups:**
```python
# 1. Standard library
import os
import sys

# 2. Third-party
from PySide6.QtCore import QUrl
import darkdetect

# 3. Local
from src.backend.application.gateways.score_gateway import ScoreGateway
```

### Naming

| Type | Convention | Example |
|------|------------|---------|
| Class | PascalCase | `TextSourceGateway`, `LoadTextUseCase` |
| Function/Variable | snake_case | `load_text`, `source_key` |
| File | snake_case / lowercase with underscores | `text_source_gateway.py` |
| Constant | UPPER_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |

### Type Hints

**ALL** function parameters and return values **MUST** have type hints.

```python
# Good
def load_text(self, source_key: str) -> str | None: ...

# Bad - missing
def load_text(self, source_key): ...
```

### Line Length
- Max 88 chars (ruff default)
- Long imports/URLs allowed to exceed

### Exceptions
- External I/O (network/file) **MUST** have exception handling
- Network exceptions: `infrastructure/network_errors.py`
- Global → user message: `application/exception_handler.py`

## Qt/QML

### Python/Qt
- Use `Signal()` + `@Slot()` for connections
- Blocking operations **MUST** run in background worker (`QRunnable` via `QThreadPool`)
- Follow `BaseWorker` pattern

### QML
- Use `Property` + `notify signal` for reactive updates
- Prefer signal-slot over direct property access
- Colors: `Theme.currentTheme.colors.*`
- Normal UI font follows the global app font set in `main.py`; only dedicated reading/typing areas should set a custom `fontFamily` (current example: `TypingPage.qml` uses LXGW WenKai for正文区)
- Name conflict: `import RinUI as Rin` then `Rin.TextArea`

## Architecture Rules (MUST Follow)

1. **Domain Services are pure** → **NO** `import PySide6` in `domain/services/`
2. **Dependency inward only** → outer → inner, never reverse
3. **Program to interface** → use Ports (protocols) for external deps
4. **Routing in Application** → Adapters **don't** make routing decisions

## Common Pitfalls (AVOID!)

### 1. TypingService.clear() → DO NOT zero char_count/wrong_char_count

**Problem:** QML `onTextChanged` is async → get negative position error:
```
QTextCursor::setPosition: Position 'X' out of range
```

**Correct:**
```python
def clear(self) -> None:
    self._state.session_stat.time = 0.0
    self._state.session_stat.key_stroke_count = 0
    # DON'T clear here → QML async issue
    # self._state.session_stat.char_count = 0
    # self._state.session_stat.wrong_char_count = 0
```

**Correct clearing:** `set_total_chars()` clears when safe.

### 2. handle_committed_text deletion order

**Correct:** process → clear deleted → update char_count **last**
```python
else:
    # process deletions
    for i in range(len(s)): ...

    # clear deleted AFTER processing
    if grow_length < 0:
        char_count = self._state.session_stat.char_count  # use BEFORE value
        for i in range(char_count + grow_length, char_count):
            char_updates.append((i, "", False))

    self._state.session_stat.char_count += grow_length  # update LAST
```

**Wrong:** update char_count before processing → wrong indices

## Documentation

- Public methods should have docstring if not obvious
- Keep docstrings concise
- Update `docs/ARCHITECTURE.md` when changing layer boundaries, object responsibilities, or main data flows
- Update `docs/DEVELOPING.md` when changing startup, developer workflow, or onboarding-critical steps

## Verification Checklist ✅

- [ ] Imports in correct order
- [ ] All functions have type hints
- [ ] Naming follows conventions
- [ ] Zero Qt imports in Domain layer
- [ ] All tests pass: `uv run pytest`
- [ ] Lint passes: `uv run ruff check .`
- [ ] Format passes: `uv run ruff format --check .`

## See Also

- [typetype-architecture](../typetype-architecture/SKILL.md) - Architecture rules
- [typetype-adding-feature](../typetype-adding-feature/SKILL.md) - Adding new features workflow
