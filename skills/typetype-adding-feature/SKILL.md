---
name: typetype-adding-feature
description: Step-by-step workflow for adding new features to TypeType, following architecture/coding standards. Use when adding a feature, modifying, or fixing bugs.
---

# TypeType: Adding New Feature Workflow

Follow these steps **IN ORDER**.

---

## Step 1: Understand & Plan

1. Read requirement carefully
2. Check `typetype-architecture` for layering rules
3. Identify which layers to modify

**Decision: Need UseCase?**

| Situation | Decision |
|-----------|----------|
| Requires cross-component orchestration/routing | ✅ Create UseCase in `application/usecases/` |
| Single pure business service call | ✅ Adapter → Domain directly, NO UseCase |

**Decision: Need new Port?**

| Situation | Decision |
|-----------|----------|
| New external dep that could have multiple implementations | ✅ Define protocol in `ports/` |
| One implementation only, not expected to vary | ❌ No Port needed |

---

## Step 2: Identify Files

| Feature Type | Files to modify/create |
|--------------|------------------------|
| New text source | 1. `ports/text_provider.py` (if new protocol)<br>2. `integration/xxx.py` (impl)<br>3. Update `config/config.example.json` if a new source key is needed<br>4. Update `main.py` injection and/or `TextSourceGateway` only if routing changes<br>5. Add test |
| New business | 1. `domain/services/xxx.py`<br>2. `presentation/adapters/xxx.py`<br>3. `presentation/bridge.py` (signals/slots if needed)<br>4. Add test |
| New UI page | 1. `src/qml/pages/Page.qml`<br>2. Update `Main.qml` nav<br>3. `bridge.py` if needed<br>4. Python adapter if needed |
| New persistence | 1. `ports/repo.py` (protocol)<br>2. `integration/sqlite-repo.py` (impl)<br>3. Domain Service uses it<br>4. Add test |

---

## Step 3: Verify Architecture Rules BEFORE Coding

- [ ] No forbidden dependencies (e.g., Qt import in Domain)
- [ ] Business routing in Application (not Adapter)
- [ ] Domain is pure business logic → NO Qt
- [ ] Dependency direction correct: `Presentation → Application → Domain/Ports → Integration`

---

## Step 4: Write Code

- Follow `typetype-coding-standards` for naming/types/imports
- Write tests alongside code → `tests/test_xxx.py`
- TDD: write failing test first → write code → pass

---

## Step 5: Local Verification

Run these **locally** and fix any issues:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

---

## Step 6: Update Documentation

- New public API → update relevant docs
- Architecture changed → update `docs/ARCHITECTURE.md`

---

## Step 7: Commit

Use the repository Lore commit format: lead with **why the change exists**, then add trailers for constraints, rejected alternatives, confidence, scope risk, and verification.

```text
<intent line: why>

<body: rationale>

Constraint: <external constraint>
Confidence: <low|medium|high>
Scope-risk: <narrow|moderate|broad>
Tested: <verification>
Not-tested: <gaps>
```

---

## Decision Guide (Quick Reference)

| Question | Answer |
|----------|--------|
| Do I need a UseCase? | Coordinate multiple components? → Yes |
| Can Adapter call Domain directly? | Yes, single service call no orchestration → Yes |
| Do I need a Port? | Multiple implementations possible? → Yes |
| Does Domain need Qt? | **NEVER** → Domain must stay pure |
| Can Adapter route? | **NO** → routing belongs in Application/Gateway |

---

## Example: Add New Text Provider

1. Protocol exists: `ports/text_provider.py`
2. Implement: `integration/springboot_text_provider.py`
3. Inject: `main.py` → replace or extend the injected `TextProvider`
4. Config: `config/config.example.json` → add text source if the UI should expose it
5. Test: `tests/test_springboot.py`
6. Verify: `uv run pytest && uv run ruff check .`
7. Commit with Lore protocol trailers describing why, constraints, and verification

Done!

## Final Quality Checklist ✅

- [ ] Architecture rules followed
- [ ] All functions have type hints
- [ ] Naming follows conventions
- [ ] Tests added
- [ ] All existing tests pass
- [ ] Lint passes
- [ ] Format passes
- [ ] Docs updated if needed
- [ ] App runs locally without errors

## See Also

- [typetype-architecture](../typetype-architecture/SKILL.md) - Architecture layering
- [typetype-development](../typetype-development/SKILL.md) - Commands workflow
- [typetype-coding-standards](../typetype-coding-standards/SKILL.md) - Coding style
