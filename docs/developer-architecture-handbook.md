# TypeType 开发者架构手册

> 最后更新：2026-04-02

本文档面向项目开发者，说明当前代码组织、分层边界、依赖规则、开发流程与协作规范。

---

## 1. 架顶总览

### 1.1 分层关系

```
QML UI (RinUI 框架)
  ↓
Presentation Layer (Bridge + Adapters)
  ↓
Application Layer (UseCases + Gateways)
  ↓
Domain Services + Ports
  ↓
Integration / Infrastructure
```

### 1.2 核心原则

- **Presentation Layer** 负责 UI 交互适配，不承载业务规则。
- **Application Layer** 负责业务流程编排、异常转换、跨组件协作。
- **Domain Layer** 负责纯业务逻辑与状态计算，不依赖 Qt。
- **Ports** 负责抽象依赖定义，隔离具体实现。
- **Integration/Infrastructure** 负责外部系统实现与技术细节。

---

## 2. 目录结构与职责

### 2.1 项目根目录

```
typetype/
├── main.py              # 依赖注入入口
├── RinUI/               # 第三方 QML 框架（vendored，不修改）
├── config/               # 配置文件（config.json, text_source_config.py）
├── resources/             # 资源文件（fonts, images, texts）
├── src/
│   ├── backend/           # Python 后端代码
│   │   ├── application/
│   │   ├── config/
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   ├── integration/
│   │   ├── models/
│   │   ├── presentation/
│   │   ├── security/
│   │   ├── utils/
│   │   └── workers/
│   └── qml/              # QML UI 代码
└── docs/                 # 项目文档
```

### 2.2 后端目录详解

```
src/backend/
├── application/
│   ├── exception_handler.py  # 全局异常处理器
│   ├── gateways/           # Gateway 实现（如 ScoreGateway）
│   ├── ports/              # 协议定义（抽象依赖）
│   └── usecases/           # 用例编排（如 LoadTextUseCase）
├── config/
│   └── runtime_config.py   # 运行时配置管理
├── domain/
│   └── services/           # 纯业务逻辑服务
├── infrastructure/
│   ├── api_client.py       # HTTP 客户端
│   └── network_errors.py    # 网络错误模型
├── integration/              # Port 具体实现
├── models/
│   ├── entity/             # 领域实体
│   └── dto/                # 数据传输对象
├── presentation/
│   ├── adapters/           # Qt 适配层
│   └── bridge.py           # QML 通信入口
├── security/                 # 安全与加密
├── utils/                    # 通用工具
└── workers/                   # 后台任务
```

---

## 3. 分层边界与依赖规则

### 3.1 允许的依赖方向

- `presentation → application/domain`（通过明确接口调用）
- `application → ports/domain/models`
- `domain → ports/models`
- `integration → ports/infrastructure/models/config`
- `config → models/config`

### 3.2 禁止的依赖方向

- `domain → Qt/PySide`
- `domain → presentation`
- `usecase → Qt 类型`
- `presentation → repository 私有实现细节`
- `integration → models/config`（使用来自 `config/` 的配置）

### 3.3 实践中的边界样例

- ✅ `Bridge` 调用 `TypingAdapter.handleCommittedText()`
- ✅ `LoadTextUseCase` 调用 `TextProvider.fetch_text_by_key()`
- ✅ `AuthService` 依赖 `AuthProvider` 协议
- ❌ `Bridge` 直接访问 `CharStatsService._repo`
- ❌ `Domain Service` 直接操作 `QThreadPool`
- ❌ `Integration` 依赖 `models/entity`（使用来自 `config/` 的配置模型）

---

## 4. 核心组件职责说明

### 4.1 Presentation Layer

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **Bridge** | QML 通信入口：属性代理、信号转发、Slot 入口、全局键盘监听器持有 | `presentation/bridge.py` |
| **TypingAdapter** | Qt 适配：计时器管理、文本着色、信号发射 | `presentation/adapters/typing_adapter.py` |
| **TextAdapter** | Qt 适配：文本加载请求与 Worker 协调 | `presentation/adapters/text_adapter.py` |
| **AuthAdapter** | Qt 适配：登录/登出信号转换 | `presentation/adapters/auth_adapter.py` |
| **CharStatsAdapter** | Qt 适配：薄弱字查询结果信号转换 | `presentation/adapters/char_stats_adapter.py` |

### 4.2 Application Layer

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **LoadTextUseCase** | 文本加载流程编排（网络/本地/剪贴板路由 + 业务验证） | `application/usecases/load_text_usecase.py` |
| **GlobalExceptionHandler** | 网络异常 → 用户友好消息集中映射 | `application/exception_handler.py` |
| **ScoreGateway** | DTO 转换 + 剪贴板操作 | `application/gateways/score_gateway.py` |

### 4.3 Domain Layer

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **TypingService** | 打字统计（SessionStat 状态、键数累积、字符统计调用） | `domain/services/typing_service.py` |
| **CharStatsService** | 字符统计（缓存管理、异步持久化、薄弱字查询） | `domain/services/char_stats_service.py` |
| **AuthService** | 认证服务（登录、token 生命周期、会话状态） | `domain/services/auth_service.py` |

### 4.4 Integration / Infrastructure Layer

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **RemoteTextProvider** | 远程文本获取实现（实现 TextProvider 协议） | `integration/remote_text_provider.py` |
| **QtLocalTextLoader** | 本地文本加载实现（支持 qrc 与文件路径） | `integration/qt_local_text_loader.py` |
| **SqliteCharStatsRepository** | 字符统计 SQLite 持久化实现 | `integration/sqlite_char_stats_repository.py` |
| **ApiClientAuthProvider** | 基于 ApiClient 的认证实现 | `integration/api_client_auth_provider.py` |
| **ApiClient** | HTTP 客户端与错误模型 | `infrastructure/api_client.py` |
| **QtAsyncExecutor** | Qt 异步任务执行器 | `integration/qt_async_executor.py` |

### 4.5 Port 协议

| 协议 | 职责 | 文件位置 |
|------|------|----------|
| **TextProvider** | 文本提供者抽象接口 | `application/ports/text_provider.py` |
| **LocalTextLoader** | 本地文本加载器抽象接口 | `application/ports/local_text_loader.py` |
| **ClipboardReader/Writer** | 剪贴板读写抽象接口 | `application/ports/clipboard.py` |
| **CharStatsRepository** | 字符统计持久化抽象接口 | `application/ports/char_stats_repository.py` |
| **AuthProvider** | 认证提供者抽象接口 | `application/ports/auth_provider.py` |

---

## 5. 依赖注入（Composition Root）

所有对象在 `main.py` 中组装，推荐顺序：

1. **Infrastructure**（ApiClient）
2. **Integration**（RemoteTextProvider, QtLocalTextLoader, SqliteCharStatsRepository 等）
3. **Gateways**（ScoreGateway）
4. **UseCases**（LoadTextUseCase）
5. **Domain Services**（CharStatsService, TypingService, AuthService）
6. **Presentation Adapters**（TypingAdapter, TextAdapter 等）
7. **Bridge**（统一 QML 通信）

这保证了"抽象先于实现、上层依赖下层接口"的构建顺序。

### 5.1 依赖注入示例

```python
# Infrastructure 层
api_client = ApiClient(timeout=runtime_config.api_timeout)
local_text_loader = QtLocalTextLoader()

# JWT token 提供函数
def _get_jwt_token() -> str:
    return SecureStorage.get_jwt("current_user") or ""

text_provider = RemoteTextProvider(
    base_url=runtime_config.base_url,
    api_client=api_client,
    token_provider=_get_jwt_token,  # 通过函数注入 token，避免直接依赖
)

# Gateways
score_gateway = ScoreGateway(clipboard=clipboard)

# UseCases
load_text_usecase = LoadTextUseCase(
    text_provider=text_provider,
    local_text_loader=local_text_loader,
    clipboard_reader=clipboard,
)

# Domain Services
char_stats_service = CharStatsService(repository=char_stats_repo, async_executor=async_executor)
typing_service = TypingService(char(Stats_service=char_stats_service)
auth_service = AuthService(auth_provider=auth_provider)

# Adapters
typing_adapter = TypingAdapter(typing_service=typing_service, score_gateway=score_gateway)
text_adapter = TextAdapter(runtime_config=runtime_config, load_text_usecase=load_text_usecase)

# Bridge
bridge = Bridge(
    typing_adapter=typing_adapter,
    text_adapter=text_adapter,
    ...
)
```

---

## 6. 新功能开发流程

### 场景 A：新增一种文本来源

1. 在 `application/ports` 复用或定义新协议
2. 在 `integration` 增加实现
3. 在 `config/text_source_config.py` 添加来源配置
4. 在 `main.py` 注入到 `LoadTextUseCase`
5. 补 `LoadTextUseCase` 与 integration 测试

### 场景 B：新增一个 UI 交互能力

1. 优先放到 `TypingAdapter` / `TextAdapter`
2. Bridge 仅新增必要的 Property/Slot/Signal 转发
3. 若涉及业务流程，放到 UseCase 或 Domain Service
4. 补对应测试（避免只测 UI）

### 场景 C：新增业务规则

1. 优先实现于 `domain/services`
2. 如需跨组件编排，在 UseCase 层组织
3. 避免把规则塞到 Bridge/Adapter

---

## 7. 测试与质量门槛

### 7.1 最低检查项

提交前至少通过：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### 7.2 测试优先级

1. `domain/services`（纯逻辑，最快反馈）
2. `application/usecases`（业务流程）
3. `integration`（外部接口与异常路径）
4. `presentation`（仅关键桥接行为）

---

## 8. 常见反模式与规避

| 反模式 | 规避方式 |
|--------|----------|
| Bridge 变成业务逻辑中心 | Bridge 只做入口和转发，业务逻辑放到 Service/UseCase |
| Domain 直接依赖具体 HTTP 客户端 | 通过 `ports` 注入协议 |
| UseCase 只剩"薄转发"却层数不断增加 | 当编排价值不足时，合并或简化层次 |
| 文档仍保留旧命名导致认知漂移 | 改架构时同步更新 README/AGENTS/docs 索引 |
| Integration 直接依赖 models/entity | 使用来自 `config/` 的配置模型 |
| 配置模型放在 models/ | 放在 `config/` 目录 |

---

## 9. 文档协作约定

- 架构改动时，至少同步更新：
  - `README.md`（对外架构说明）
  - `AGENTS.md`（开发约束）
  - `docs/README.md`（文档索引）
- 优先使用当前术语：
  - `LoadTextUseCase`
  - `ScoreGateway`
  - `Presentation = Bridge + Adapters`

---

## 10. 相关阅读

- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [guide.md.guide.md)
- [roadmap.md](./roadmap.md)
- [spring-boot-backend-design.md](./spring-boot-backend-design.md)
