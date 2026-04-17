---
name: typetype-development
description: TypeType development workflow, environment setup, testing, building, CI, and pre-commit checks. Use when setting up or preparing code for commit.
---

# TypeType Development

## Quick Setup

**Prerequisites**: Python 3.12+, `uv` package manager

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone + install
git clone <repo> && cd typetype && uv sync

# Run
uv run python main.py
```

## First Files to Read

For a fast mental model of the current project, read these first:

1. `main.py`
2. `src/backend/presentation/bridge.py`
3. `src/backend/presentation/adapters/text_adapter.py`
4. `src/backend/application/usecases/load_text_usecase.py`
5. `src/backend/application/gateways/text_source_gateway.py`
6. `src/backend/domain/services/typing_service.py`

## Common Commands

```bash
# TESTING
uv run pytest                      # all tests
uv run pytest tests/test_file.py   # single file
uv run pytest -v                  # verbose

# CODE QUALITY
uv run ruff check .               # lint check
uv run ruff format --check .      # format check
uv run ruff format .              # auto format

# LOGGING
TYPETYPE_DEBUG=1 uv run python main.py          # debug enabled
TYPETYPE_LOG_LEVEL=info uv run python main.py  # set level: debug/info/warning/error/none
```

## Pre-Commit Checklist (MUST DO)

Before commit, **all must pass locally**:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Fix any failure before commit.

## Commit Convention

Repository commits follow the **Lore Commit Protocol**: describe **why** first, then record constraints, rejected options, confidence, scope risk, and what was verified.

Recommended template:

```text
<intent line: why this change was made>

<body: context, constraints, rationale>

Constraint: <external constraint>
Rejected: <alternative> | <reason>
Confidence: <low|medium|high>
Scope-risk: <narrow|moderate|broad>
Directive: <warning for future modifiers>
Tested: <what was verified>
Not-tested: <known gaps>
```

## Packaging (Nuitka)

```bash
uv run python -m ensurepip --upgrade
uv pip install --upgrade nuitka

uv run python -m nuitka main.py \
  --follow-imports \
  --enable-plugin=pyside6 \
  --include-qt-plugins=qml \
  --include-package=RinUI \
  --include-data-dir=RinUI=RinUI \
  --include-data-dir=config=config \
  --output-dir=deployment \
  --quiet \
  --noinclude-qt-translations \
  --standalone \
  --noinclude-dlls=libQt6WebEngine* \
  --include-data-dir=src/qml=src/qml \
  --include-data-dir=resources/texts=resources/texts \
  --include-data-files=resources/images/TypeTypeLogo.png=resources/images/TypeTypeLogo.png \
  --include-data-files=resources/fonts/*-subset.ttf=resources/fonts/
```

**Windows add:**
```
--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*
```

**Font subsetting**: Always use `*-subset.ttf` to reduce package size.

**⚠️ 打包配置同步清单**: 修改 Nuitka `--include-data-*` 参数时，必须同步更新以下 5 个位置：
1. `AGENTS.md`
2. `README.md`
3. `docs/DEVELOPING.md`
4. `skills/typetype-development/SKILL.md`
5. `.github/workflows/build-release.yml` — 两处都要改：
   - "准备构建目录"步骤：`cp -a` / `Copy-Item` 中添加目录
   - "运行打包"步骤：Nuitka 命令中添加 `--include-data-dir` 参数

## Git Workflow

- `main` branch: stable, always deployable
- Feature: `feature/name` or `fix/name`
- All CI checks must pass before merge

## CI Checks (GitHub Actions)

| Workflow | Checks |
|----------|--------|
| `ci.yml` | ruff check + format check |
| `multi-platform-tests.yml` | pytest on Linux / Windows |
| `build-release.yml` | Nuitka build |

## Platform Notes

**Linux Wayland global keyboard** needs `input` group:

```bash
sudo usermod -aG input $USER
```
Log out and back in. Without permission, app degrades gracefully - still works.

## Final Commit Checklist ✅

- [ ] All tests pass locally
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] No new lint warnings
- [ ] Feature works when run locally
- [ ] Docs updated if changed

## See Also

- [typetype-architecture](../typetype-architecture/SKILL.md) - Architecture rules
- [typetype-coding-standards](../typetype-coding-standards/SKILL.md) - Coding style
- [typetype-adding-feature](../typetype-adding-feature/SKILL.md) - Adding new features workflow
