# TypeType 架构设计手册

> 最后更新：2026-04-06
>
> 本文档描述 **当前客户端实现**。若其他文档与其冲突，以当前源码和本文为准。

---

## 目录

- [一句话先理解项目](#一句话先理解项目)
- [当前实现快照](#当前实现快照)
- [分层架构](#分层架构)
- [目录结构](#目录结构)
- [核心对象装配（mainpy）](#核心对象装配mainpy)
- [核心数据流](#核心数据流)
  - [文本加载链路](#文本加载链路)
  - [从剪贴板载文](#从剪贴板载文)
  - [打字统计链路](#打字统计链路)
  - [薄弱字查询链路](#薄弱字查询链路)
  - [认证链路](#认证链路)
- [依赖规则](#依赖规则)
- [修改一个功能时怎么判断改哪里](#修改一个功能时怎么判断改哪里)
- [新开发者推荐阅读顺序](#新开发者推荐阅读顺序)
- [常见误区](#常见误区)

---

## 一句话先理解项目

TypeType 是一个 **PySide6 + QML 桌面打字练习应用**：

- QML 负责页面与交互
- `Bridge + Adapters` 负责 Qt/QML 适配
- `UseCases + Gateways` 负责编排与边界整合
- `Domain Services` 负责纯业务逻辑
- `Ports + Integration` 负责替换型外部依赖

如果你只记一句：**QML 不直接碰业务，Domain 不直接碰 Qt。**

---

## 当前实现快照

截至 2026-04-06，当前代码里的稳定事实包括：

- 启动入口：`main.py`
- QML 根页面：`src/qml/Main.qml`
- 当前唯一明确承担“业务编排”的 UseCase：`LoadTextUseCase`
- 当前主要业务服务：`TypingService`、`CharStatsService`、`AuthService`
- 当前文本来源实现：`RemoteTextProvider` + `QtLocalTextLoader`
- 当前字符统计持久化：`SqliteCharStatsRepository`
- 当前 Python/QML 通信门面：`presentation/bridge.py`

---

## 分层架构

```text
QML UI
  -> Presentation (Bridge + Adapters)
  -> Application (UseCases + Gateways)
  -> Domain / Ports
  -> Integration / Infrastructure
```

### 各层职责

| 层 | 当前组件 | 职责 |
|----|----------|------|
| QML | `src/qml/` | 页面、交互、布局、局部 UI 状态 |
| Presentation | `Bridge` | QML 门面：属性代理、信号转发、Slot 入口 |
| Presentation | `TypingAdapter` / `TextAdapter` / `AuthAdapter` / `CharStatsAdapter` | Qt 适配、线程协调、错误回传 |
| Application | `LoadTextUseCase` | 文本加载编排入口 |
| Application | `TextSourceGateway` / `ScoreGateway` / `GlobalExceptionHandler` | 来源路由、DTO/剪贴板、异常消息映射 |
| Domain | `TypingService` / `CharStatsService` / `AuthService` | 纯业务逻辑、状态管理、统计计算 |
| Ports | `TextProvider` / `LocalTextLoader` / `Clipboard*` / `AuthProvider` / `CharStatsRepository` | 抽象协议 |
| Integration | `RemoteTextProvider` / `QtLocalTextLoader` / `ApiClientAuthProvider` / `SqliteCharStatsRepository` 等 | Port 实现 |
| Infrastructure | `ApiClient` / `network_errors.py` | 通用 HTTP 客户端、网络异常分类 |

---

## 目录结构

### Python 后端

```text
src/backend/
├── application/
│   ├── exception_handler.py
│   ├── gateways/
│   │   ├── score_gateway.py
│   │   └── text_source_gateway.py
│   └── usecases/
│       └── load_text_usecase.py
├── config/
│   └── runtime_config.py
├── domain/services/
│   ├── auth_service.py
│   ├── char_stats_service.py
│   └── typing_service.py
├── infrastructure/
│   ├── api_client.py
│   └── network_errors.py
├── integration/
│   ├── api_client_auth_provider.py
│   ├── global_key_listener.py
│   ├── noop_char_stats_repository.py
│   ├── qt_async_executor.py
│   ├── qt_local_text_loader.py
│   ├── remote_text_provider.py
│   ├── sqlite_char_stats_repository.py
│   └── system_identifier.py
├── models/
│   ├── dto/
│   └── entity/
├── ports/
├── presentation/
│   ├── bridge.py
│   └── adapters/
├── security/
├── utils/
└── workers/
```

### QML 侧

```text
src/qml/
├── Main.qml
├── pages/
│   ├── TypingPage.qml
│   ├── WeakCharsPage.qml
│   ├── DailyLeaderboard.qml
│   ├── WeeklyLeaderboard.qml
│   ├── AllTimeLeaderboard.qml
│   ├── ProfilePage.qml
│   └── SettingsPage.qml
├── typing/
│   ├── ToolLine.qml
│   ├── UpperPane.qml
│   ├── ScoreArea.qml
│   ├── LowerPane.qml
│   ├── HistoryArea.qml
│   └── EndDialog.qml
└── components/
    └── AppText.qml
```

---

## 核心对象装配（main.py）

当前对象装配顺序如下：

```text
RuntimeConfig
  -> ApiClient / QtLocalTextLoader / QtAsyncExecutor
  -> RemoteTextProvider / SqliteCharStatsRepository / ApiClientAuthProvider
  -> ScoreGateway / TextSourceGateway / LoadTextUseCase
  -> CharStatsService / TypingService / AuthService
  -> TypingAdapter / TextAdapter / AuthAdapter / CharStatsAdapter
  -> Bridge
  -> appBridge 注入 QML
```

### 关键点

- `main.py` 是唯一装配根；没有全局 service locator
- `Bridge` 是 QML 能看到的唯一后端门面
- Wayland 下会额外创建 `GlobalKeyListener`
- 字符统计在应用退出前会 `flush()` 一次

---

## 核心数据流

### 文本加载链路

```text
ToolLine.qml
  -> appBridge.requestLoadText(sourceKey)
  -> Bridge.requestLoadText(sourceKey)
  -> TextAdapter.requestLoadText(sourceKey)
  -> LoadTextUseCase.plan_load(sourceKey)
  -> TextSourceGateway.get_execution_mode(sourceKey)
  -> sync / async
  -> LoadTextUseCase.load(sourceKey)
  -> TextSourceGateway.load_text_by_key(sourceKey)
  -> QtLocalTextLoader 或 RemoteTextProvider
  -> TextAdapter 发射 textLoaded / textLoadFailed
  -> TypingPage.applyLoadedText(...)
```

### 文本加载里各层到底负责什么

| 组件 | 做什么 | 不做什么 |
|------|--------|----------|
| `TextAdapter` | Qt 信号、线程协调、本地同步/远程异步执行 | 不做来源路由决策 |
| `LoadTextUseCase` | 输出执行计划、统一文本加载入口 | 不直接碰 Qt |
| `TextSourceGateway` | 查配置、决定本地还是远程、调用 Port | 不管 UI 状态 |
| `QtLocalTextLoader` | 读本地文件 | 不含业务路由 |
| `RemoteTextProvider` | 发 HTTP 请求取文本 | 不含 UI/线程逻辑 |

### 从剪贴板载文

这条链路不经过 `TextSourceGateway`：

```text
ToolLine.qml
  -> appBridge.loadTextFromClipboard()
  -> TextAdapter.loadTextFromClipboard()
  -> LoadTextUseCase.load_from_clipboard()
  -> ClipboardReader.text()
  -> TextAdapter 发射结果信号
```

---

### 打字统计链路

```text
QML 输入事件
  -> Bridge.handlePressed() / handleCommittedText()
  -> TypingAdapter
  -> TypingService
  -> SessionStat / wrong_char_prefix_sum 更新
  -> CharStatsService.accumulate(...)
  -> 会话结束时 flush_async()
  -> SqliteCharStatsRepository.save_batch(...)
```

### 这一段为什么是 `Adapter -> Domain` 直连

因为当前打字统计没有跨多个边界对象的编排需求：

- 计时器、文本着色、信号发射：Qt 责任，放在 `TypingAdapter`
- 计数、速度、错误数、字符统计：业务责任，放在 `TypingService`

如果强行再包一层“打字相关 UseCase”，大概率只会变成纯转发。

---

### 薄弱字查询链路

```text
WeakCharsPage.qml
  -> appBridge.loadWeakChars()
  -> CharStatsAdapter.loadWeakChars()
  -> WeakCharsQueryWorker
  -> CharStatsService.get_weakest_chars(10)
  -> SqliteCharStatsRepository.get_weakest_chars(10)
  -> Adapter 发射 weakestCharsLoaded
  -> QML 渲染列表
```

---

### 认证链路

```text
ProfilePage.qml
  -> appBridge.login(username, password)
  -> AuthAdapter.login(...)
  -> AuthService.login(...)
  -> ApiClientAuthProvider.login(...)
  -> ApiClient.request(...)
  -> SecureStorage 保存 token
  -> Bridge 转发登录状态变化信号
```

启动时还会执行：

```text
main.py
  -> bridge.initializeLoginState()
  -> AuthService.initialize()
  -> validate_token() / refresh_token()
```

---

## 依赖规则

### 允许的依赖方向

```text
Bridge -> Adapters
Adapters -> Application
Adapters -> Domain（仅纯业务服务直连场景）
Application -> Domain / Ports / Config
Integration / Infrastructure -> Ports / Domain
```

### 明确禁止

```text
Presentation -> Integration / Infrastructure
Domain -> Qt / PySide / QML
UseCase -> Qt 类型
Adapter 做业务来源路由
```

### RuntimeConfig 的边界

| 用法 | 是否允许 |
|------|----------|
| `TextSourceGateway` 持有并做来源路由 | ✅ |
| `TextAdapter` 持有并做 UI 来源展示 | ✅ |
| `TextAdapter` 依据配置做业务决策 | ❌ |
| QML 直接读取配置文件做路由 | ❌ |

---

## 修改一个功能时怎么判断改哪里

### 场景 1：新增一个文本来源

通常会改：

- `config/config.example.json`
- `config/text_source_config.py`（如果配置模型要扩展）
- `RuntimeConfig`
- `TextSourceGateway` / `RemoteTextProvider`（如需新路由或协议）
- 对应测试

### 场景 2：新增一个纯统计规则

通常会改：

- `TypingService` 或 `CharStatsService`
- 相关 entity / DTO
- 相关测试

### 场景 3：新增一个新的 QML 能力

通常会改：

- 对应 QML 页面
- `Bridge`
- 对应 `Adapter`
- 必要时增加 worker

### 场景 4：新增一个跨组件业务流程

通常会改：

- `application/usecases/`
- 必要的 gateway / port
- adapter 只负责调用它，不负责编排

---

## 新开发者推荐阅读顺序

1. `main.py`
2. `src/qml/Main.qml`
3. `src/backend/presentation/bridge.py`
4. `src/backend/presentation/adapters/text_adapter.py`
5. `src/backend/application/usecases/load_text_usecase.py`
6. `src/backend/application/gateways/text_source_gateway.py`
7. `src/backend/presentation/adapters/typing_adapter.py`
8. `src/backend/domain/services/typing_service.py`

这套顺序可以让你先建立“页面 -> Bridge -> Adapter -> UseCase/Service”的脑图，再下钻细节。

---

## 常见误区

### 误区 1：所有业务都必须经过 UseCase

不是。当前代码明确允许：

- **有编排价值** → UseCase
- **单个纯业务服务调用** → Adapter 直连 Domain Service

### 误区 2：`TextAdapter` 持有 `RuntimeConfig` 就代表它在做业务路由

不是。它目前只做：

- 来源列表展示
- 默认来源展示

真正的业务路由仍在 `TextSourceGateway`。

### 误区 3：Domain 完全不碰外部对象，所以不能依赖 Repository 协议

Domain 可以依赖 **抽象协议（Port）**，不能依赖 **具体 Qt / HTTP / SQLite 实现**。

### 误区 4：QML 不允许指定任何字体

普通 UI 字体由 `main.py` 统一设置；但打字阅读区在 `TypingPage.qml` 中对正文使用了专用阅读字体，这是当前实现的一部分。

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-06 | 基于当前源码重写：补充对象装配、QML 页面结构、真实数据流与边界判断 |
| 2026-04-03 | 重写文本加载闭口后的边界规则 |
| 2026-03-21 | 首次创建 |
