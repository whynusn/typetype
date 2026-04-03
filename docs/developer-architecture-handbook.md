# TypeType 开发者架构手册

> 最后更新：2026-04-03
>
> 本文档是 `docs/` 下关于客户端架构的唯一事实来源。若其他文档中的架构描述与本文冲突，以本文和当前源码为准。

---

## 1. 当前架构概览

项目采用清晰的分层架构，文本加载链路现已由 Application 完整拥有边界决策：

```text
QML UI
  ->
Presentation
  Bridge + Adapters
  ->
Application
  UseCases + Gateways
  ->
Domain
  Services + Entities
  ->
Ports
  抽象依赖协议
  ->
Integration / Infrastructure
  具体实现
```

**关键修复（2026-04-03）**：
- 新增 `TextSourceGateway`：负责配置查询和 Port 适配
- `LoadTextUseCase` 恢复为编排入口：接收 `source_key` 而非已解析对象
- `LoadTextUseCase.plan_load()` 负责给出同步/异步执行计划
- `TextAdapter` 保留 `RuntimeConfig` 依赖：仅用于 UI 配置展示，不做业务路由或执行策略判断

---

## 2. 文本加载链路（最终形态）

### 2.1 完整调用链

```text
QML: ToolLine.requestLoadText(source_key)
  ->
Bridge: requestLoadText(source_key)
  ->
TextAdapter: requestLoadText(source_key)
  ->
LoadTextUseCase: plan_load(source_key)
  - 输出 execution_mode（sync / async）
  ->
TextAdapter: 执行同步调用或入队 Worker
  ->
LoadTextUseCase: load(source_key)
  ->
TextSourceGateway: load_text_by_key(source_key)
  - 读取 RuntimeConfig（配置查询）
  - 决定走本地还是网络（业务路由）
  ->
LocalTextLoader / TextProvider / Clipboard
```

### 2.2 各层职责

| 组件 | 层级 | 职责 | 关键点 |
|--------|--------|------|----------|
| `TextAdapter` | Presentation | Qt 信号、线程协调、错误回传 | ✅ 可用 RuntimeConfig 展示 UI 选项<br>✅ 仅执行 Application 给出的同步/异步计划 |
| `LoadTextUseCase` | Application | 文本加载编排入口 | ✅ 接收 `source_key`，输出执行计划<br>✅ 统一错误处理 |
| `TextSourceGateway` | Application | 配置查询 + Port 适配 | ✅ 持有 RuntimeConfig 做业务路由<br>✅ 调用相应的 Port |
| `LocalTextLoader` | Port | 本地文件读取协议 | 协议定义，无业务逻辑 |
| `TextProvider` | Port | 远程文本获取协议 | 协议定义，无业务逻辑 |
| `ClipboardReader` | Port | 剪贴板读取协议 | 协议定义，无业务逻辑 |

### 2.3 依赖关系

```
TextAdapter
  └─> LoadTextUseCase
       ├─> plan_load(source_key) -> execution_mode
       └─> TextSourceGateway
            ├─> RuntimeConfig (配置查询)
            ├─> TextProvider (网络)
            └─> LocalTextLoader (本地)

TextAdapter
  └─> RuntimeConfig (仅用于 UI 配置展示)
```

---

## 3. 其他主要链路

### 3.1 打字统计链路

```text
QML: TypingPage.handlePressed()
  ->
Bridge: handlePressed()
  ->
TypingAdapter: handlePressed()
  ->
TypingService: accumulate_key()
  ->
CharStatsService: accumulate()
  ->
SqliteCharStatsRepository (异步持久化)
```

**特点**：
- `TypingAdapter` 直连 `TypingService`：纯业务服务，无需额外 UseCase
- 字符统计通过 `CharStatsService` 异步持久化

### 3.2 认证链路

```text
QML: ProfilePage.login(username, password)
  ->
Bridge: login(username, password)
  ->
AuthAdapter: login(username, password)
  ->
AuthService: login(username, password)
  ->
ApiClientAuthProvider: login()
  ->
ApiClient (HTTP 请求)
```

### 3.3 分数处理链路

```text
TypingAdapter: 打字完成
  ->
ScoreGateway: build_score_message()
  - 将 SessionStat 转换为 ScoreSummaryDTO
  ->
ScoreGateway: copy_score_to_clipboard()
  - 通过 ClipboardWriter 协议
```

---

## 4. 架构原则

### 4.1 核心原则

1. **清晰的依赖方向**：Presentation → Application → Domain → Ports
2. **UseCase 只在有编排价值时保留**：避免纯转发
3. **Adapter 可直连纯业务服务**：无需为简单调用塞 UseCase
4. **RuntimeConfig 的使用规范**：
   - ✅ Gateway 持有并做业务路由
   - ✅ Adapter 持有并做 UI 配置展示
   - ❌ Adapter 不做业务路由决策
   - ❌ Adapter 不读取配置决定同步/异步执行策略

### 4.2 允许的依赖

```
Bridge → Adapters
Adapters → Application UseCases
Adapters → Domain Services (纯业务服务时)
Application → Domain / Ports / Config
Integration → Ports / Infrastructure
```

### 4.3 禁止的依赖

```
Presentation → Integration / Infrastructure
Domain → Qt / PySide
UseCase → Qt 类型
Adapter 做业务路由决策
```

---

## 5. 目录结构与关键文件

```
src/backend/
├── application/
│   ├── gateways/
│   │   ├── score_gateway.py          # DTO 转换 + 剪贴板
│   │   └── text_source_gateway.py   # 文本来源路由
│   ├── ports/                      # 抽象依赖协议
│   │   ├── text_provider.py
│   │   ├── local_text_loader.py
│   │   └── clipboard.py
│   └── usecases/
│       └── load_text_usecase.py    # 文本加载编排
├── config/
│   └── runtime_config.py           # 运行时配置
├── domain/
│   ├── models/entity/              # 领域实体
│   └── services/                  # 纯业务服务
│       ├── typing_service.py
│       ├── auth_service.py
│       └── char_stats_service.py
├── integration/                   # Port 的具体实现
│   ├── remote_text_provider.py
│   ├── qt_local_text_loader.py
│   └── api_client_auth_provider.py
├── infrastructure/                # 基础设施
│   └── api_client.py
├── presentation/
│   ├── bridge.py                  # QML 门面
│   └── adapters/                 # Qt 适配层
│       ├── text_adapter.py
│       ├── typing_adapter.py
│       ├── auth_adapter.py
│       └── char_stats_adapter.py
└── workers/                     # 后台任务
    └── text_load_worker.py
```

---

## 6. 给新开发者的指引

### 6.1 快速理解三句话

1. **Bridge 是 QML 门面**：不涉及业务规则
2. **Application 层负责编排**：UseCase 负责流程，Gateway 负责边界适配
3. **Domain 层是纯业务**：Service 做业务规则，Entity 是数据模型

### 6.2 阅读顺序

1. `main.py` - 离解依赖注入
2. `presentation/bridge.py` - 理解 QML 通信方式
3. 按功能看对应 Adapter - 了解 Qt 适配模式
4. 需要流程编排时看 UseCase / Gateway
5. 需要业务规则时看 Domain Service

### 6.3 修改建议

| 想要... | 应该... | 示例 |
|----------|----------|--------|
| 添加新 UI 功能 | 修改 Bridge + Adapter | 新属性/信号/Slot |
| 添加新业务流程 | 创建 UseCase | 如：`SubmitScoreUseCase` |
| 添加外部依赖 | 定义 Port + 实现 | 如：`DataExporter` 协议 |
| 添加纯业务规则 | 修改 Domain Service | 如：速度计算公式 |
| 添加数据持久化 | 通过 Service + Repository | 如：`SqliteScoreRepository` |

---

## 7. 常见问题

### Q1: 为什么 `TextAdapter` 可以持有 `RuntimeConfig`？

A: 因为它只用配置做 **UI 展示**（`get_source_options()`、`get_default_source_key()`），不做 **业务路由决策**，也不决定同步/异步执行策略。真正配置查询、路由和执行计划都在 Application 层完成。

### Q2: 为什么 `TypingAdapter` 直连 `TypingService`，不经过 UseCase？

A: 因为打字统计是纯业务服务，没有跨组件编排需求。强制加 UseCase 只会变成纯转发，没有价值。

### Q3: 新增功能是否必须创建必须创建 UseCase？

A: 不一定。如果：
- 只涉及单个纯业务服务 → Adapter 直连 Service
- 需要跨组件协调或边界整合 → 创建 UseCase

### Q4: 如何判断是否应该创建 Gateway？

A: 如果需要：
- 配置查询 + Port 适配（如 `TextSourceGateway`）
- DTO 转换 + 剪贴板操作（如 `ScoreGateway`）
- 边界对象整合

---

## 8. 相关文档

- [docs/README.md](./README.md)
- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [guide.md](./guide.md)
- [roadmap.md](./roadmap.md)
- [spring-boot-backend-design.md](./spring-boot-backend-design.md)
