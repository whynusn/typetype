# TypeType 架构设计手册
<!-- 状态: active | 最后验证: 2026-06-04 -->

## 📍 文档导航卡（你在这里）

本文档是 **架构事实来源**（代码权威）。出现信息冲突时以本文为准。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 架构分层、数据流、依赖规则、陷阱 | [README.md](../README.md) — 快速入门<br>[AGENTS.md](../AGENTS.md) — 开发规范 | [快速开始](#快速开始)<br>[分层架构](#分层架构)<br>[数据流](#核心数据流)<br>[已知陷阱](#已知陷阱) |

---

> 最后更新：2026-06-04

---

## 快速开始

```bash
# 环境：Python 3.12+, uv 0.9.26+
uv sync
uv run python main.py
```

| 命令 | 说明 |
|:--- |:--- |
| `uv run python main.py` | 启动应用 |
| `uv run pytest` | 运行测试 |
| `uv run ruff check .` | 代码检查 |
| `uv run ruff format --check .` | 格式检查 |
| `TYPETYPE_DEBUG=1 uv run python main.py` | 调试模式 |

### 日志开关

- `TYPETYPE_DEBUG=1` — 开启 debug 日志
- `TYPETYPE_LOG_LEVEL=debug\|info\|warning\|error\|none` — 精确控制

---

## 一句话理解项目

TypeType 是一个 **PySide6 + QML 桌面打字练习应用**：

> **QML 不直接碰业务，Domain 不直接碰 Qt。**

- QML 负责页面与交互
- `Bridge + Adapters` 负责 Qt/QML 适配
- `UseCases + Gateways` 负责编排与边界整合
- `Domain Services` 负责纯业务逻辑
- `Ports + Integration` 负责替换型外部依赖

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
|:--- |:--- |:---|
| QML | `src/qml/` | 页面、交互、布局、局部 UI 状态 |
| Presentation | `Bridge` | QML 门面：属性代理、信号转发、Slot 入口 |
| Presentation | `*Adapter` | Qt 适配、线程协调、错误回传 |
| Application | `*UseCase` | 流程编排、业务验证 |
| Application | `TypingSessionContext` | 会话状态机：阶段/来源模式/分片载文 |
| Application | `*Gateway` | 来源路由、DTO/剪贴板、异常映射 |
| Domain | `*Service` | 纯业务逻辑、状态管理、统计计算 |
| Ports | 各 Port 协议 | 抽象协议 |
| Integration | 各 Port 实现 | Port 实现 |
| Infrastructure | `ApiClient` / `network_errors` | 通用 HTTP 客户端、网络异常分类 |

---

## 目录结构

### Python 后端

```
src/backend/
├── application/
│   ├── exception_handler.py
│   ├── session_context.py
│   ├── gateways/          # gateway 实现
│   └── usecases/          # usecase
├── config/                # 配置 + 容器工厂
├── domain/services/       # domain service
├── infrastructure/        # HTTP 客户端 + 异常分类
├── integration/           # Port 实现
├── models/
│   ├── dto/               # 数据传输对象
│   └── entity/            # 领域实体
├── ports/                 # 抽象协议
├── presentation/
│   ├── bridge.py          # QML 门面
│   └── adapters/          # adapter
├── security/              # 加密 + 安全存储
├── utils/                 # 日志 + 文本工具
└── workers/               # 后台 worker
```

> 完整文件树见 git 仓库。本文档不再维护逐文件列表（代码提交即变更）。

### 载文入口

| 入口 | 文件 | 触发方式 |
|:--- |:--- |:--- |
| 自定义载文 | `CustomLoadTextPage.qml` | TypingPage F2 / 侧边栏 |
| 本地文库 | `LocalArticlesPage.qml` | 侧边栏 |
| 练单器 | `TrainerPage.qml` | 侧边栏 |
| 极速杯 | `JisuBeiPage.qml` | 侧边栏 |

共享组件：`SliceCriteriaPanel`（达标条件）、`TextLoadPanel`（文本输入/选择）。

---

## 核心数据流

### 文本加载链路

```
ToolLine.qml
  -> appBridge.requestLoadText(sourceKey)
  -> Bridge -> TextAdapter
  -> LoadTextUseCase.plan_load(sourceKey)
  -> TextSourceGateway -> TextLoadPlan
  -> TextLoadWorker（后台线程）
  -> LoadTextUseCase.load(plan)
  -> QtLocalTextLoader 或 RemoteTextProvider
  -> Adapter emit textLoaded() -> TypingPage.applyLoadedText()
```

### 打字统计链路

```
QML 输入事件
  -> Bridge -> TypingAdapter
  -> TypingService（计数、速度、错误数）
  -> CharStatsService.accumulate()
  -> flush_async()
  -> SqliteCharStatsRepository.save_batch()
```

### 薄弱字查询链路

```
WeakCharsPage.qml
  -> appBridge.loadWeakChars(n, sortMode, weights)
  -> CharStatsAdapter -> WeakCharsQueryWorker
  -> CharStatsService -> SqliteCharStatsRepository
  -> Adapter emit weakestCharsLoaded -> QML 渲染
```

### 认证链路

```
ProfilePage.qml
  -> appBridge.login() -> AuthAdapter
  -> AuthService -> ApiClientAuthProvider
  -> ApiClient -> SecureStorage 保存 token
```

### 服务地址配置链路

```
SettingsPage.qml
  -> appBridge.setBaseUrl(url)
  -> Bridge.base_url_update_callback()  // 闭包，上抛到 main.py
  -> RuntimeConfig.update_base_url()    // strip + 派生 URL + 持久化
  -> 遍历 url_dependent 列表传播 URL
  -> Bridge.emit(baseUrlChanged)        // QML 属性绑定刷新
```

> **设计要点**：Bridge 不直接依赖 Integration 对象，通过回调闭包上抛到装配层处理。

---

## 依赖规则

### 允许的依赖方向

```text
Bridge -> Adapters
Adapters -> Application
Adapters -> Domain（仅纯业务服务直连）
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
|:--- |:--- |
| `TextSourceGateway` 持有并做来源路由 | ✅ |
| `TextAdapter` 持有并做 UI 展示 | ✅ |
| `TextAdapter.get_base_url()` 代理只读属性 | ✅ |
| `TextAdapter` 依据配置做业务决策 | ❌ |
| Bridge 直接依赖 RuntimeConfig | ❌ |
| Bridge 直接持有 Integration 对象 | ❌ |

---

## 修改一个功能时怎么判断改哪里

| 场景 | 通常改 |
|:--- |:--- |
| 新增文本来源 | `config/` → `text_source_gateway.py` → `RemoteTextProvider` → 测试 |
| 新增统计规则 | `TypingService` / `CharStatsService` → entity/DTO → 测试 |
| 新增 QML 能力 | QML 页面 → `Bridge` → 对应 `Adapter` → 必要时加 worker |
| 新增跨组件业务流程 | `application/usecases/` → gateway/port → adapter 调用 |

---

## 已知陷阱（架构设计类）

> **分类说明**：编码实践类陷阱见 [AGENTS.md § 已知陷阱](../AGENTS.md#8-已知陷阱)。

### 误区 1：所有业务都必须经过 UseCase

不是。**有编排价值 → UseCase**，**单服务调用 → Adapter 直连 Domain Service**。强行包一层纯转发 UseCase 只会增加间接层。

### 误区 2：`TextAdapter` 持有 `RuntimeConfig` 等于做业务路由

不是。它目前只做来源列表展示和默认来源展示。业务路由在 `TextSourceGateway`。

### 误区 3：Domain 不能依赖 Repository 协议

Domain 可以依赖 **抽象协议（Port）**，不能依赖 **具体实现（SQLite / HTTP / Qt）**。

### 误区 4：QML 不允许指定任何字体

普通 UI 字体由 `main.py` 统一设置；但 `TypingPage.qml` 对正文使用了专用阅读字体，这是当前实现。

### StackView 生命周期时序陷阱

`Connections.enabled: StackView.status === StackView.Active` 守卫时，`StackView.onActivating` 发出的信号会被丢弃。必须用：

```
onActivating → 只做状态重置
onActivated → Qt.callLater() 延迟触发信号
```

相关决策见 [ADR-003：单实例页面导航](./decisions/003-single-instance-page-navigation.md)。

---

## 后续方向

| 优先级 | 方向 |
|:--- |:--- |
| 高 | 基于薄弱字自动生成练习材料 |
| 中 | 远端同步字符统计 / AI Typing Coach |
| 低 | 更细粒度学习分析 |

---

## RinUI 本地修改概要

RinUI 是 vendored 第三方框架。必要的修改记录在 `RinUI/LOCAL_MODIFICATIONS.md`。

当前已记录的修改：
1. `ContextMenu.qml` — 下拉弹出位置修复 + height 动画修复
2. `NavigationBar.qml` — Back 按钮水平对齐
3. `NavigationView.qml` — StackView 重构为单实例
4. `FluentPage.qml` — 移除 OpacityMask（GPU 阻塞）+ anchors 替换为 x/y

---

## 当前限制

客户端暂无防作弊措施，服务端亦未做防攻击处理。部分依赖服务端信任链的功能（排行榜、成绩提交）可能数据不可靠。
