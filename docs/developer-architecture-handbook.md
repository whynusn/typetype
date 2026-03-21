# TypeType 开发者架构手册

> 最后更新：2026-03-21
>
> 本文档面向项目开发者，说明当前代码组织、分层边界、依赖规则、开发流程与协作约定。

---

## 1. 手册目标

这份手册用于统一团队对当前架构的认知，重点解决三个问题：

1. **代码放哪一层**（目录与职责）
2. **该依赖谁，不该依赖谁**（依赖方向与边界）
3. **如何在不破坏架构的前提下开发新功能**（实践流程）

---

## 2. 当前架构总览

### 2.1 分层关系

```text
QML UI
  ↓
Presentation Layer (Bridge + Adapters)
  ↓
Application Layer (UseCases + Gateways)
  ↓
Domain Services + Ports
  ↓
Integration / Infrastructure
```

### 2.2 核心原则

- `Presentation` 负责 UI 交互适配，不承载业务规则。
- `Application` 负责业务流程编排、异常转换、跨组件协作。
- `Domain` 负责纯业务逻辑与状态计算，不依赖 Qt。
- `Ports` 负责抽象依赖定义，隔离具体实现。
- `Integration/Infrastructure` 负责外部系统实现与技术细节。

---

## 3. 目录与职责映射

### 3.1 目录结构（后端）

```text
src/backend/
├── application/
│   ├── gateways/      # Port 适配 + 异常转换
│   ├── ports/         # 协议定义（抽象依赖）
│   └── usecases/      # 用例编排
├── config/            # RuntimeConfig
├── domain/
│   └── services/      # 纯业务逻辑
├── infrastructure/    # ApiClient 与网络异常模型
├── integration/       # Port 具体实现
├── models/            # entity / dto / text_source
├── presentation/
│   ├── adapters/      # Qt 适配层
│   └── bridge.py      # appBridge
├── security/          # 安全与存储
├── utils/             # 通用工具
└── workers/           # 后台任务
```

### 3.2 Bridge 为什么属于 Presentation

`bridge.py` 位于 `presentation/` 是有意设计，而非例外：

- Bridge 本质上是 **QML 通信入口 Facade**。
- 它使用 Qt 的 `QObject/Property/Signal/Slot`，属于 UI 适配代码。
- 它不实现领域规则，只负责转发到 Adapter / Service 边界。

结论：**Presentation Layer = Bridge + Adapters**。

---

## 4. 分层边界与依赖规则

### 4.1 允许的依赖方向

- `presentation -> application/domain`（通过明确接口调用）
- `application -> ports/domain/models`
- `domain -> ports/models`
- `integration -> ports/infrastructure/models`

### 4.2 禁止的依赖方向

- `domain -> Qt/PySide`
- `domain -> presentation`
- `usecase -> Qt 类型`
- `presentation -> repository 私有实现细节`

### 4.3 实践中的边界样例

- ✅ `Bridge` 调用 `TypingAdapter.handleCommittedText()`
- ✅ `LoadTextUseCase` 调用 `LoadTextGateway.fetch_from_network()`
- ✅ `AuthService` 依赖 `AuthProvider` 协议
- ❌ `Bridge` 直接访问 `CharStatsService._repo`
- ❌ `Domain Service` 直接操作 `QThreadPool`

---

## 5. 关键组件职责

### 5.1 Presentation

- `Bridge`：QML 属性代理、信号转发、Slot 入口
- `TypingAdapter`：Qt 文本对象、光标、信号桥接
- `TextAdapter`：文本加载请求与 worker 协调

### 5.2 Application

- `LoadTextUseCase`：文本加载流程编排与异常映射
- `TypingUseCase`：成绩消息、历史记录等编排
- `TextGateway`：来源解析、network/local/catalog 路由
- `ScoreGateway`：DTO 组装、剪贴板输出

### 5.3 Domain

- `TypingService`：会话统计、字符计数、状态维护
- `CharStatsService`：字符统计缓存、预热、持久化调度
- `AuthService`：登录、token 生命周期、会话状态

### 5.4 Integration / Infrastructure

- `SaiWenTextFetcher`：第三方文本接口实现
- `QtLocalTextLoader`：本地文本读取实现
- `SqliteCharStatsRepository`：字符统计持久化实现
- `ApiClient`：HTTP 客户端与错误模型

---

## 6. 依赖注入（Composition Root）

所有对象在 `main.py` 组装，推荐顺序：

1. Infrastructure
2. Integration
3. Gateways
4. UseCases
5. Domain Services
6. Presentation Adapters
7. Bridge

这保证了“抽象先于实现、上层依赖下层接口”的构建顺序。

---

## 7. 新功能开发流程（建议）

### 场景 A：新增一种文本来源

1. 在 `application/ports` 定义或复用协议
2. 在 `integration` 增加实现
3. 在 `main.py` 注入到 `TextGateway`
4. 更新 `RuntimeConfig` 来源配置
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

## 8. 测试与质量门槛

### 8.1 最低检查项

提交前至少通过：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### 8.2 测试优先级

1. `domain/services`（纯逻辑，最快反馈）
2. `application/usecases`（业务流程）
3. `integration`（外部接口与异常路径）
4. `presentation`（仅关键桥接行为）

---

## 9. 常见反模式与规避

- 反模式：Bridge 变成业务逻辑中心
  - 规避：Bridge 只做入口和转发

- 反模式：Domain 直接依赖具体 HTTP 客户端
  - 规避：通过 `ports` 注入协议

- 反模式：UseCase 只剩“薄转发”却层数不断增加
  - 规避：当编排价值不足时，合并或简化层次

- 反模式：文档仍保留旧命名导致认知漂移
  - 规避：改架构时同步更新 README/AGENTS/docs 索引

---

## 10. 文档协作约定

- 架构改动时，至少同步更新：
  - `README.md`（对外架构说明）
  - `AGENTS.md`（开发约束）
  - `docs/README.md`（文档索引）

- 优先使用当前术语：
  - `LoadTextUseCase` / `TypingUseCase`
  - `TextGateway` / `ScoreGateway`
  - `Presentation = Bridge + Adapters`

---

## 11. 相关阅读

- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [guide.md](./guide.md)
- [roadmap.md](./roadmap.md)
- [spring-boot-backend-design.md](./spring-boot-backend-design.md)
