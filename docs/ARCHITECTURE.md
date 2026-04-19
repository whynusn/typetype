# TypeType 架构设计手册

> 最后更新：2026-04-17
>
> 本文档描述 **当前客户端实现**。若其他文档与其冲突，以当前源码和本文为准。

---

## 目录

- [快速开始](#快速开始)
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
- [已知陷阱](#已知陷阱)
- [后续方向](#后续方向)

---

## 快速开始

```bash
# 环境：Python 3.12+, uv 0.9.26+
uv sync
uv run python main.py
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `uv run python main.py` | 启动应用 |
| `uv run pytest` | 运行测试 |
| `uv run ruff check .` | 代码检查 |
| `uv run ruff format --check .` | 格式检查 |
| `uv run ruff format .` | 自动格式化 |
| `TYPETYPE_DEBUG=1 uv run python main.py` | 调试模式启动 |

### 日志开关

默认只输出 warning 及以上。通过环境变量调整：

- `TYPETYPE_DEBUG=1` — 开启 debug 日志
- `TYPETYPE_LOG_LEVEL=debug|info|warning|error|none` — 精确控制

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

截至 2026-04-16，当前代码里的稳定事实包括：

- 启动入口：`main.py`
- QML 根页面：`src/qml/Main.qml`
- 当前唯一明确承担”业务编排”的 UseCase：`LoadTextUseCase`
- 当前主要业务服务：`TypingService`、`CharStatsService`、`AuthService`
- 当前文本来源实现：`RemoteTextProvider` + `QtLocalTextLoader`
- 当前字符统计持久化：`SqliteCharStatsRepository`
- 当前 Python/QML 通信门面：`presentation/bridge.py`
- 当前成绩提交实现：`ApiClientScoreSubmitter`（只发 textId，无回调/重试）
- 文本入库方式：管理员 API 上传 或 服务端自动抓取（如 SaiWen）
- 只有服务端存在的文本才能提交成绩，本地文件/剪贴板仅用于练习

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
| Presentation | `TypingAdapter` / `TextAdapter` / `AuthAdapter` / `CharStatsAdapter` / `LeaderboardAdapter` / `UploadTextAdapter` | Qt 适配、线程协调（所有 I/O 走 Worker）、错误回传 |
| Application | `LoadTextUseCase` | 文本加载编排入口 |
| Application | `TextSourceGateway` / `ScoreGateway` / `LeaderboardGateway` / `GlobalExceptionHandler` | 来源路由、DTO/剪贴板、异常消息映射 |
| Workers | `BaseWorker` / `TextLoadWorker` / `LeaderboardWorker` / `TextListWorker` / `CatalogWorker` / `WeakCharsQueryWorker` | 后台任务执行、异常统一处理 |
| Domain | `TypingService` / `CharStatsService` / `AuthService` | 纯业务逻辑、状态管理、统计计算 |
| Ports | `TextProvider` / `LocalTextLoader` / `Clipboard*` / `AuthProvider` / `CharStatsRepository` / `TextUploader` / `ScoreSubmitter` / `LeaderboardProvider` / `AsyncExecutor` | 抽象协议 |
| Integration | `RemoteTextProvider` / `QtLocalTextLoader` / `ApiClientAuthProvider` / `SqliteCharStatsRepository` / `LeaderboardFetcher` 等 | Port 实现 |
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
│   │   ├── text_source_gateway.py
│   │   └── leaderboard_gateway.py
│   └── usecases/
│       └── load_text_usecase.py
├── config/
│   ├── runtime_config.py
│   └── text_source_config.py
├── domain/services/
│   ├── auth_service.py
│   ├── char_stats_service.py
│   └── typing_service.py
├── infrastructure/
│   ├── api_client.py
│   └── network_errors.py
├── integration/
│   ├── api_client_auth_provider.py
│   ├── api_client_score_submitter.py
│   ├── global_key_listener.py
│   ├── noop_char_stats_repository.py
│   ├── qt_async_executor.py
│   ├── qt_local_text_loader.py
│   ├── remote_text_provider.py
│   ├── sqlite_char_stats_repository.py
│   ├── system_identifier.py
│   ├── text_uploader.py
│   └── leaderboard_fetcher.py
├── models/
│   ├── dto/
│   │   ├── auth_dto.py
│   │   ├── fetched_text.py
│   │   ├── score_dto.py
│   │   └── text_catalog_item.py
│   └── entity/
│       ├── char_stat.py
│       └── session_stat.py
├── ports/
│   ├── auth_provider.py
│   ├── char_stats_repository.py
│   ├── clipboard.py
│   ├── local_text_loader.py
│   ├── score_submitter.py
│   ├── text_provider.py
│   ├── text_uploader.py
│   ├── async_executor.py
│   └── leaderboard_provider.py
├── presentation/
│   ├── bridge.py
│   └── adapters/
│       ├── typing_adapter.py
│       ├── text_adapter.py
│       ├── auth_adapter.py
│       ├── char_stats_adapter.py
│       ├── leaderboard_adapter.py
│       └── upload_text_adapter.py
├── security/
│   ├── crypt.py
│   └── secure_storage.py
├── utils/
│   ├── logger.py
│   └── text_id.py
└── workers/
    ├── base_worker.py
    ├── catalog_worker.py
    ├── text_load_worker.py
    ├── leaderboard_worker.py
    ├── text_list_worker.py
    └── weak_chars_query_worker.py
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
│   ├── SettingsPage.qml
│   ├── TextLeaderboardPage.qml
│   └── UploadTextPage.qml
├── typing/
│   ├── ToolLine.qml
│   ├── UpperPane.qml
│   ├── ScoreArea.qml
│   ├── LowerPane.qml
│   ├── HistoryArea.qml
│   ├── EndDialog.qml
│   └── LeaderboardPanel.qml
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
  -> ApiClientScoreSubmitter / TextUploader
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
  -> TextSourceGateway.plan_load(sourceKey)
  -> TextLoadPlan（无论本地还是网络，统一走 Worker）
  -> TextLoadWorker（后台线程）
  -> LoadTextUseCase.load(plan)
  -> TextSourceGateway.load_from_plan(sourceEntry)
  -> QtLocalTextLoader 或 RemoteTextProvider
  -> TextAdapter 发射 textLoaded(text, text_id, source_label) / textLoadFailed
  -> TypingPage.applyLoadedText(...)
```

**text_id 生成时机：**
- 本地文本：`_load_from_local()` 只读文件立即返回（text_id=None）；TextAdapter 启动后台 daemon thread 异步调用 `TextSourceGateway.lookup_text_id()` 回查服务端，成功后通过 `localTextIdResolved` 信号 → Bridge.setTextId()
- 网络文本：由服务器返回

### 文本加载里各层到底负责什么

| 组件 | 做什么 | 不做什么 |
|------|--------|----------|
| `TextAdapter` | Qt 信号、线程协调、**所有加载统一走 Worker**（包括本地来源） | 不做来源路由决策，不在主线程做同步 I/O |
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
  -> appBridge.loadWeakChars(n, sortMode, weights)
  -> CharStatsAdapter.loadWeakChars(n, sort_mode, weights)
  -> WeakCharsQueryWorker
  -> CharStatsService.get_weakest_chars(n, sort_mode, weights)
  -> SqliteCharStatsRepository.get_chars_by_sort(sort_mode, weights, n)
  -> Adapter 发射 weakestCharsLoaded
  -> QML 渲染列表
```

排序模式：`error_rate`（默认）| `error_count` | `weighted`（需传 `weights` dict）。

打字结束后 `typingEnded` 信号触发 WeakCharsPage 自动刷新薄弱字列表。

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
- `src/backend/config/text_source_config.py`（如果配置模型要扩展）
- `RuntimeConfig`
- `src/backend/models/dto/text_catalog_item.py`（如果目录 DTO 要扩展）
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

## 已知陷阱

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

## RinUI 本地修改记录

RinUI 是 vendored 第三方框架（`RinUI/`），原则上不修改，但以下修改是必要的性能和正确性修复。
详细变更记录见 `RinUI/LOCAL_MODIFICATIONS.md`（如有）。

| # | 文件 | 修改 | 原因 |
|---|------|------|------|
| 1 | `RinUI/components/ContextMenu.qml` | 下拉弹出位置从垂直居中改为 `y: parent.height`，移除 `Behavior on y` | ComboBox 下拉菜单先原地展开再滑动到居中位置，不符合标准下拉行为。居中 y 随 height 动画重算 + y 的平滑动画导致滑动效果 |
| 2 | `RinUI/components/Navigation/NavigationBar.qml` | Back 按钮 `anchors.leftMargin` 补偿 `windowDragArea` 偏移 | FluentWindow 标题栏 Back 按钮与 NavigationBar 导航项水平不对齐（偏左约 5px），因 title Row 在 TitleBar 坐标系而 NavigationBar 主体有 `windowDragArea` 偏移 |
| 3 | `RinUI/components/Navigation/NavigationView.qml` | 添加 `property bool loggedin: false`，页面创建时传递给各页面 | Main.qml 的登录状态需要传递给所有页面实现统一登录状态管理，NavigationView 作为中间层传递属性 |
| 4 | `RinUI/windows/FluentPage.qml` | 移除 `layer.effect: OpacityMask` 及 `Qt5Compat.GraphicalEffects` 依赖 | `OpacityMask` 强制 GPU 同步离屏渲染，每次页面切换都阻塞主线程。FluentPage 的 `Flickable.clip: true` + `appLayer` 背景已提供足够的视觉效果，圆角裁切不必要 |
| 5 | `RinUI/components/ContextMenu.qml` | `enter` transition 中高度动画前加 `PauseAnimation { duration: 16 }` | 首次打开 popup 时 ListView 未完成布局，`implicitHeight` 读到 0 导致动画到 6px 后缩回。一帧延迟给 ListView 时间完成布局 |
| 6 | `RinUI/windows/FluentPage.qml` | `container`（ColumnLayout）的 `anchors.top` + `anchors.topMargin` + `anchors.horizontalCenter` 替换为 `y` + `x` 属性绑定 | ColumnLayout 自身使用 anchors 会导致其子项触发 "Detected anchors on an item that is managed by a layout" 运行时警告；`x`/`y` 属性绑定功能等价且避免 anchors 与 Layout 机制冲突 |

新增修改时请在此表追加记录。

---

## 版本历史

|| 日期 | 变更 |
||------|------|
|| 2026-04-19 | FluentPage `container` 的 anchors 替换为 x/y 属性绑定（消除 ColumnLayout 与 anchors 冲突警告）；RinUI 修改记录 #6 |
|| 2026-04-19 | 本地文本加载拆分两阶段：`_load_from_local()` 只读文件立即返回（text_id=None），TextAdapter 后台 daemon thread 异步回查服务端 text_id（`lookup_text_id`），通过 `localTextIdResolved` 信号 → Bridge.setTextId() 更新排行榜。修复 `QTimer.singleShot` lambda 静默失败问题，改用 Qt 原生 QueuedConnection 跨线程信号 |
|| 2026-04-17 | 目录树补全：models/dto（+auth_dto/fetched_text/score_dto）、models/entity（+char_stat/session_stat）、security/（+crypt/secure_storage）、utils/（+logger）；ports 末尾改为 `└──` |
|| 2026-04-16 | TextAdapter 移除 `_load_sync`，所有文本加载统一走 Worker（本地来源内含同步 HTTP 回查 `_lookup_server_text_id`，不能在主线程执行）；FluentPage 移除 `layer.effect: OpacityMask`（GPU 离屏渲染阻塞页面切换）；RinUI ContextMenu 的 `height` 动画从 `enter` transition 改为 `Behavior on height`（修复首次打开缩回问题） |
|| 2026-04-15 | 补全文档遗漏：新增 LeaderboardProvider/AsyncExecutor 端口、LeaderboardGateway/Adapter/Worker、TextListWorker、WeakCharsQueryWorker、UploadTextAdapter、text_id 工具等 |
|| 2026-04-13 | 架构重构：只有服务端文本才能提交成绩；客户端移除 hash 计算；删除无感上传回调链路；source_key 不再进入成绩提交链路 |
|| 2026-04-11 | 新增 TextUploader Port、text_id 生成逻辑、无感上传链路；移除配置中 text_id 字段 |
|| 2026-04-06 | 基于当前源码重写：补充对象装配、QML 页面结构、真实数据流与边界判断 |
|| 2026-04-03 | 重写文本加载闭口后的边界规则 |
|| 2026-03-21 | 首次创建 |

---

## 当前限制

> 客户端暂无防作弊措施，服务端亦未做防攻击处理。部分依赖服务端信任链的功能（如排行榜、成绩提交）在当前阶段可能无法正常使用或数据不可靠，待安全机制完善后逐步开放。

---

## 后续方向

### 高优先级

- **推荐练习**：基于 `CharStatsService.get_weakest_chars()` 自动生成有针对性的练习材料

### 中优先级

- **远端同步字符统计**：把本地 `CharStat` 数据同步到服务端，多设备共享
- **Spring Boot 服务端接入**：替换第三方 API 为自托管文本服务（详见 `docs/history/spring-boot-design.md`）
- **AI Typing Coach**：基于薄弱字的个性化文本生成（详见 `docs/history/ai-agent-plan.md`）

### 低优先级

- 更细粒度学习分析
