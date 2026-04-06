---
name: typetype-architecture
description: Understand TypeType project architecture, layering rules, dependency directions, and component responsibilities. Use when working on TypeType, adding features, or refactoring.
---

# TypeType Architecture

## Overview

TypeType = PySide6/QML typing practice app. **Clean Architecture + Ports & Adapters**.

**Dependency direction (MUST follow):**
```
QML UI → Presentation → Application → Domain/Ports → Integration/Infrastructure
```

## Directory Structure

```
src/backend/
├── application/
│   ├── exception_handler.py  # Global exception → user message mapping
│   ├── gateways/
│   │   ├── score_gateway.py      # DTO conversion + clipboard
│   │   └── text_source_gateway.py # Text source routing + Port adapter
│   └── usecases/
│       └── load_text_usecase.py # Text loading orchestration
├── ports/             # Protocol definitions (top-level)
│   ├── async_executor.py
│   ├── auth_provider.py
│   ├── char_stats_repository.py
│   ├── clipboard.py
│   ├── local_text_loader.py
│   ├── ranking_repository.py
│   └── text_provider.py
├── config/
│   └── runtime_config.py  # Text sources configuration
├── domain/
│   └── services/        # Pure business logic (NO Qt dependency)
│       ├── typing_service.py
│       ├── auth_service.py
│       └── char_stats_service.py
├── models/             # Data models
│   ├── entity/          # Domain entities (char_stat, session_stat)
│   └── dto/             # Data transfer objects
├── infrastructure/      # Infrastructure
│   ├── api_client.py    # HTTP client wrapper
│   └── network_errors.py # Network error classification
├── integration/         # Port implementations
├── presentation/
│   ├── bridge.py       # QML facade (appBridge)
│   └── adapters/       # Qt adaptation layer
├── security/           # Encryption + secure storage
├── utils/              # Logger
└── workers/            # Background tasks (QRunnable)
```

## Layering Rules (MUST Follow)

### ✅ ALLOWED Dependencies

```
Bridge → Adapters
Adapters → Application (UseCases/Gateways)
Adapters → Domain (pure business calls directly)
Application → Domain / Ports / Config
Integration / Infrastructure → Ports / Domain
```

### ❌ FORBIDDEN Dependencies

```
Presentation → Integration / Infrastructure   # Breaks dependency inversion
Domain → Qt / PySide / QML                   # Domain must be pure business
UseCases → Qt types                         # UseCases must not depend on Qt
Adapter makes business routing decisions    # Routing → Application layer only
```

### RuntimeConfig Rules

| Usage | Allowed |
|-------|--------|
| Gateway holds + makes routing decisions | ✅ YES |
| Adapter shows for UI (source list, default) | ✅ YES |
| Adapter makes business routing decisions | ❌ NO |
| Adapter decides sync/async execution strategy | ❌ NO |

## Component Responsibilities

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| QML UI | `src/qml/` | Display, user interaction |
| Presentation | `Bridge` | QML facade: property proxy, signal forwarding |
| Presentation | `Adapters` | Qt adaptation: thread coordination |
| Application | `UseCases` | Business process orchestration |
| Application | `Gateways` | Config query, Port adaptation, DTO conversion |
| Domain | `Services` | Pure business logic, NO Qt dependency |
| Ports | Protocols | Abstract dependency interface |
| Integration | Implementations | Qt/SQLite/HTTP concrete implementations |

## Key Data Flow: Text Loading

```
QML → Bridge → TextAdapter → LoadTextUseCase.plan_load() → outputs sync/async
                    ↓
              TextAdapter executes or enqueues → LoadTextUseCase.load()
                    ↓
              TextSourceGateway routes → Local/Network → result → QML
```

## When to Create What

| You want... | Create/Modify... |
|-------------|-----------------|
| Add new UI feature | Bridge + Adapter |
| Add business process | UseCase (Application) |
| Add external dependency | Define Port + implement Integration |
| Add pure business rule | Domain Service |
| Add data persistence | Domain Service + Port + Integration |

## Non-Negotiable Principles

1. **Clear dependency direction** always
2. **UseCase only when needed** - no pure-forwarding UseCases
3. **Adapter can call Domain directly** - no forced UseCase
4. **Domain is pure business** - NO Qt import EVER

## RinUI Rules

- `RinUI/` = vendored third-party → **DO NOT MODIFY**
- `pyproject.toml` excludes `RinUI` from ruff → keep
- QML colors: `Theme.currentTheme.colors.*`
- Normal UI font follows the global app font set in `main.py`; only dedicated reading/typing areas should set a custom `fontFamily` (current example: `TypingPage.qml` uses LXGW WenKai for正文区)
- Name conflict: `import RinUI as Rin`

## Verification Checklist ✅

- [ ] Dependency direction correct (no forbidden deps)
- [ ] Business routing in Application (not Adapter)
- [ ] Domain Services have zero Qt imports
- [ ] All tests pass: `uv run pytest`
- [ ] Lint passes: `uv run ruff check .`
