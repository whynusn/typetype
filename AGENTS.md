# typetype 项目开发指南

## 📍 文档导航卡（你在这里）

本文档面向 **AI 开发者**，记录编码规范和已知陷阱。若不确定信息来源，参见 [docs/meta/README.md](./docs/meta/README.md)（全局文档规范）。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 开发约束、编码规范、已知陷阱 | [README.md](./README.md) — 快速入门<br>[ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 架构权威 | [代码风格](#3-代码风格)<br>[已知陷阱](#8-已知陷阱) |

---

## 🧭 AI 阅读顺序

如果你是第一次接触此项目的 AI Agent，建议按以下顺序阅读：

1. **本文档 §3 代码风格 + §8 已知陷阱** — 编码约束和常见坑位（最高优先级）
2. **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — 架构分层、数据流、依赖规则（事实来源）
3. **[docs/reference/README.md](./docs/reference/README.md)** — 配置字段、Bridge API、QML 页面速查
4. **本文档 §4-7** — 测试策略、服务端接入、平台权限、CI 要求
5. **`skills/` 目录** — 特定场景的操作手册（如添加功能、架构分析）

> 已熟悉项目后，日常开发只需查阅 **§3 代码风格 + §8 已知陷阱** 即可。

> 特定场景操作（如添加功能、架构分析、调试）可查阅 `skills/` 目录下的操作手册。

---

## 📚 文档维护指南（AI Agent 必读）

### 文档职责速查

| 文档 | 我的角色 | 什么时候更新我 |
| :--- | :--- | :--- |
| `ARCHITECTURE.md` | 唯一事实来源（"宪法"） | 新增/删除文件、架构变更、发现新陷阱 |
| **本文档** | AI 开发约束与陷阱集 | 发现新坑位、编码规范变化、验证要求更新 |
| `docs/reference/*` | 速查表（配置/QML/API） | 新增配置字段、修改 Bridge Slot、新增 API 端点 |
| `docs/history/*` | 历史设计文档归档 | 完成重大功能、修复复杂 bug、记录设计决策 |
| `docs/meta/README.md` | 文档规范与同步规则 | 文档结构变化、权威优先级调整 |

### 修改代码后的文档更新流程

```
1. 改完代码
   ↓
2. 判断变更类型（见下表）
   ↓
3. 更新对应文档（保持同步）
   ↓
4. 验证：运行 docs/meta/README.md § 验证清单
```

| 我改了什么 | 需要更新哪里 | 检查要点 |
| :--- | :--- | :--- |
| 新增/删除/重命名源码文件 | `ARCHITECTURE.md` § 目录结构 | 路径、文件名、注释是否一致 |
| 新增/修改配置字段 | `docs/reference/config.md` | 类型、默认值、说明是否完整 |
| 新增/删除 QML 页面 | `docs/reference/qml-pages.md` | 页面名称、信号、依赖是否准确 |
| 新增/修改 Bridge Slot/Signal | `docs/reference/bridge-slots.md` | 参数类型、返回值、使用场景 |
| 新增/修改 API 端点 | `docs/reference/api-endpoints.md` | URL、方法、请求/响应格式 |
| 发现新的**编码实践类**陷阱（代码怎么写） | **本文** § 已知陷阱 | 问题、原因、正确做法、历史记录。参见 §8 顶部说明 |
| 发现新的**架构设计类**陷阱（架构/分层） | `ARCHITECTURE.md` § 已知陷阱 | 问题、原因、方案、历史记录 |
| 架构分层变更 | `ARCHITECTURE.md` § 分层架构 + 依赖规则 | 层职责、依赖方向、绑定规则 |
| 完成重大功能/修复 | 考虑写入 `docs/history/` | 背景、决策、实现、验证结果 |

### 权威优先级（出现冲突时）

见 [docs/meta/README.md § 权威优先级](./docs/meta/README.md#权威优先级)

简版：
1. **当前源码**（最终真理）
2. `ARCHITECTURE.md`
3. `docs/reference/*`
4. **本文档** (`AGENTS.md`)
5. `skills/*`
6. `docs/history/*`

### 提交前验证清单

- [ ] `ARCHITECTURE.md` 目录结构与 `src/backend/` 实际文件一致
- [ ] `docs/reference/` 中的表格与代码一致
- [ ] `ARCHITECTURE.md` 中的陷阱是否覆盖最新发现
- [ ] 所有内部链接无断链（相对路径正确）
- [ ] 本文档的陷阱描述是否准确、完整
- [ ] 代码改动与文档更新在同一 PR/提交中

### 文档编写规范

- **事实文档**（`ARCHITECTURE.md`）：先给结论，再给解释。代码块标注语言。
- **Agent 规则**（本文档）：简洁直接。陷阱必须包含：问题、原因、正确做法、历史记录。
- **速查表**（`docs/reference/*`）：纯表格，H1 标题 + `>` 摘要行 + 表格主体。不写段落。每个文件 ≤ 200 行。
- **历史归档**（`docs/history/*`）：完整记录背景、决策、实现、验证。不修改、不删除。

---

## 1. 开发环境与命令

> 开发环境搭建和运行命令见 [ARCHITECTURE.md § 快速开始](./docs/ARCHITECTURE.md#快速开始)。

### 字体裁剪说明

项目使用了裁剪后的字体文件以减小打包体积和运行时内存占用：

| 字体 | 原始大小 | 裁剪后大小 | 减少比例 |
|:--- |:--- |:--- |:---|
| HarmonyOS Sans SC Regular | 8.2 MB | 504 KB | ~94% |
| LXGW WenKai Regular | 25.4 MB | 880 KB | ~97% |

裁剪后的字体文件（`*-subset.ttf`）仅包含项目实际使用的中文字符，打包时应使用这些裁剪版本而非原始字体文件。

## 2. 当前架构（以代码为准）

> 完整的架构文档请见 [ARCHITECTURE.md](./docs/ARCHITECTURE.md)，本文档是补充速查和陷阱案例。

完整的文件树见 [docs/ARCHITECTURE.md § 目录结构](./docs/ARCHITECTURE.md#目录结构)，此处不重复维护。

RinUI/                   # 第三方 QML 框架（本地 vendored，少量必要修改，见 docs/ARCHITECTURE.md）

### 薄弱字排序功能

薄弱字（Weak Chars）支持自定义排序模式，全链路传递排序参数：

**数据流**：WeakCharsPage.qml → Bridge → CharStatsAdapter → WeakCharsQueryWorker → CharStatsService → CharStatsRepository

**排序模式**（`CharStatsRepository.get_chars_by_sort`）：

| sort_mode | 说明 |
|:--- |:---|
| `error_rate` | 按错误率排序（默认） |
| `error_count` | 按错误次数排序 |
| `weighted` | 加权排序，权重由 `weights` 参数指定 |

weighted 模式的 `weights` 参数格式：`{"error_rate": float, "total_count": float, "error_count": float}`。

**CharStatsService.get_weakest_chars(n, sort_mode, weights)** 直接透传参数到 Repository，无额外业务逻辑。

**QML 交互**：WeakCharsPage 提供 ComboBox 选择排序模式，weighted 模式下额外显示各维度的权重 ComboBox。`typingEnded` 信号触发薄弱字列表自动刷新。

### 架构约束（防止职责混乱）

**绑定规则**：Presentation（Adapter/Bridge）只能依赖 Application 层（UseCase/Gateway），禁止依赖 Domain 层。

**决策规则**：是否走 UseCase，看是否有**流程编排/分支判断**：
- 有编排逻辑（如文本加载的来源路由）→ 必须走 UseCase
- 纯转发、无分支（如 `ScoreGateway.build_score_message`）→ Adapter 可直连 Gateway
- 有异常转换需求 → 由 BaseWorker + GlobalExceptionHandler 统一处理，UseCase 不捕获

**边界规则**：
- `GlobalExceptionHandler`：异常类型 → 用户可读消息的集中映射表
- `BaseWorker`：统一捕获后台任务异常，调用 GlobalExceptionHandler 后发射信号
- `LoadTextUseCase`：只做路由 + 业务验证，不捕获网络异常
- `TypingSessionContext`：Application 层状态机，分片业务逻辑由它承载（当前 pragmatic 选择）
- `TypingService/AuthService/CharStatsService`：纯业务规则，无 Qt 依赖
- **Bridge 禁止直接访问 `SessionContext`**，所有状态访问必须通过 `TypingAdapter` 代理，以维持 Presentation → Application 的正确依赖方向

**扩展异常**：在 `exception_handler.py` 的 `_EXCEPTION_MESSAGE_MAP` 中添加新映射即可，无需修改 UseCase。

### Bridge 职责（薄适配层）

- **属性代理**：透传各 Adapter 的只读属性到 QML（`loggedin`, `typeSpeed`, `textLoading` 等）
- **信号转发**：Adapter 发射的信号转发到 QML 层
- **Slot 入口**：QML 调用请求转发到对应 Adapter

```python
# main.py 中的依赖注入示例（工厂函数在 config/container.py 中）
infra = create_infra(runtime_config)
repos = create_repos()
providers = create_providers(runtime_config, infra)
clipboard = QApplication.clipboard()
gateways = create_gateways(runtime_config, providers, infra, repos, clipboard)
use_cases = create_use_cases(gateways, repos, clipboard)
services = create_services(infra, runtime_config)
adapters = create_adapters(services, gateways, use_cases, infra, runtime_config)

bridge = Bridge(
    typing_adapter=adapters.typing,
    text_adapter=adapters.text,
    auth_adapter=adapters.auth,
    char_stats_adapter=adapters.char_stats,
    wenlai_adapter=adapters.wenlai,
    local_article_adapter=adapters.local_article,
    ziti_adapter=adapters.ziti,
    trainer_adapter=adapters.trainer,
    font_adapter=adapters.font,
    upload_text_adapter=adapters.upload_text,
    leaderboard_adapter=adapters.leaderboard,
    typing_totals_gateway=gateways.typing_totals,
    key_listener=adapters.key_listener,
    base_url_update_callback=update_base_url,
)
```

## 3. 代码风格

### Python

- 导入顺序：标准库 -> 第三方 -> 本地
- 命名：类 `PascalCase`，函数/变量 `snake_case`
- 函数参数与返回值必须有类型提示
- 外部 I/O（网络/系统）必须有异常处理

### Qt/QML

- 使用 `Property + notify signal` 做响应式更新
- UI 不执行耗时任务，耗时逻辑走 `workers`
- RinUI `ContextMenu` 的 `height` 动画必须用 `Behavior on height`，不能在 `enter` transition 中动画（原因见已知陷阱）
- `FluentPage` 不使用 `layer.effect: OpacityMask`（GPU 离屏渲染阻塞页面切换）
- **FluentPage 内容区的直接子项必须使用 `Layout.*` 属性而非 `anchors`**：FluentPage 的 `content` 注入到内部 `container`（ColumnLayout），因此子项受 Layout 管理器控制，使用 anchors 会触发 "Detected anchors on an item that is managed by a layout" 警告
- **非 Layout 容器内的 Layout 管理器可用 anchors 定位自身**：如 `Frame { ColumnLayout { anchors.fill: parent } }` 是合法的，因为 Frame 不是 Layout 管理器
- Python 与 QML 通信优先走信号槽
- **QtQuick.Controls 必须使用限定导入 `as QQC`**：为避免与 RinUI 同名组件（Button/Frame/Dialog 等）冲突，所有 QML 文件中必须使用 `import QtQuick.Controls 2.15 as QQC` 而非 `import QtQuick.Controls 2.15`。使用 QtQuick.Controls 类型时加 `QQC.` 前缀（如 `QQC.Pane`、`QQC.ScrollView`、`QQC.ScrollBar.vertical`）。RinUI 已提供的同名类型不前缀（如 `Button`、`Frame`、`Dialog` 等从 RinUI 解析）。

## 4. 测试策略

- 优先覆盖用例层与核心逻辑，不依赖真实 UI
- 对网络错误、超时、解析异常必须有测试（由 GlobalExceptionHandler 统一转换）
- 新增文本来源时，需同时补充：
  - `LoadTextUseCase` 测试（业务验证、路由分支）
  - `GlobalExceptionHandler` 测试（新异常类型 → 用户消息映射）
  - 对应 service/integration 测试

## 5. Spring Boot 服务端接入（已接入）

当前已通过 `RemoteTextProvider`、`ApiClientScoreSubmitter`、`LeaderboardFetcher` 等接入 [typetype-server](https://github.com/whynusn/typetype-server) Spring Boot 后端。

### 接入原则

- 用例层只依赖 Port 协议（`TextProvider`、`ScoreSubmitter` 等），不直接依赖 HTTP 细节。
- Spring Boot 后端作为 integration 层实现注入，不破坏现有调用链。

### 当前使用的接口

当前接口列表见 [docs/reference/api-endpoints.md](./docs/reference/api-endpoints.md)。

### 新增服务端能力时的扩展路径

1. 在 `ports/` 定义新 Port 协议。
2. 在 `integration/` 实现对应 adapter（复用 `ApiClient`，异常映射到 `network_errors.py`）。
3. 在 `main.py` 装配层注入新实现。
4. 配置项通过 `RuntimeConfig` 管理，`base_url` 通过 `update_base_url()` 统一更新。

## 6. 平台与权限

- Linux Wayland 下，全局键盘监听通常需要 `input` 组权限。
- 不满足权限时必须优雅降级，不影响基础打字流程。

## 7. CI 对齐

- `ci.yml`: ruff check / format check
- `multi-platform-tests.yml`: Linux/Windows pytest
- `build-release.yml`: Linux/Windows Nuitka 打包与 release

所有改动提交前应至少本地通过：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 8. 已知陷阱（Critical Gotchas）

> **陷阱分类说明**：本文档记录**编码实践类陷阱**（代码怎么写才正确）。架构设计类陷阱见 [ARCHITECTURE.md § 已知陷阱](./docs/ARCHITECTURE.md#已知陷阱)。新增陷阱时：编码实践类写在这里，架构设计类写在 ARCHITECTURE.md。

### ⚠️ TypingService.clear() 不要清零 char_count 和 wrong_char_count

**问题**：在 `TypingService.clear()` 方法中，不能清零 `char_count` 和 `wrong_char_count`。

**原因**：QML 的 `onTextChanged` 事件是异步的。如果在 `clear()` 中提前清零 `char_count`，当 QML 侧尚未完成的 `onTextChanged` 事件触发时，会以 `char_count=0` 计算出负数的 `beginPos`，导致 `QTextCursor::setPosition: Position 'X' out of range` 错误。

**正确做法**：
```python
def clear(self) -> None:
    """清空统计数据。"""
    self._state.session_stat.time = 0.0
    self._state.session_stat.key_stroke_count = 0
    # ❌ 错误：不要在这里清零
    # self._state.session_stat.char_count = 0
    # self._state.session_stat.wrong_char_count = 0
    self._state.session_stat.date = ""
    self._state.last_commit_time_ms = 0.0
```

**正确的清零时机**：在 `set_total_chars()` 中清零，因为这时是安全的：
```python
def set_total_chars(self, total: int) -> None:
    """设置总字符数。"""
    self._state.total_chars = total
    self._state.session_stat.char_count = 0      # ✅ 这里清零
    self._state.session_stat.wrong_char_count = 0  # ✅ 这里清零
    self._state.wrong_char_prefix_sum = [0 for _ in range(total)]
```

**历史记录**：此问题在 2026-03-21 的架构重构中首次出现，AI Agent 在重构时错误地在 `clear()` 中清零了这两个字段，导致删除字符时出现负数位置错误。旧版本的 `_reset_session_stat()` 方法有明确注释说明不能清零。

### ⚠️ handle_committed_text 删除字符时的逻辑顺序

**正确顺序**：先处理 `s`，再更新 `char_count`，最后清除被删除位置。

**错误顺序**：先更新 `char_count`，再处理 `s`，会导致使用更新后的 `char_count` 计算出错误的位置。

```python
# ✅ 正确顺序
else:
    # 删除字符 / 纯替换
    for i in range(len(s)):
        # 处理 s 中的字符...

    # 删除时清除被删除位置
    if grow_length < 0:
        char_count = self._state.session_stat.char_count  # 使用更新前的值
        for i in range(char_count + grow_length, char_count):
            char_updates.append((i, "", False))

    self._state.session_stat.char_count += grow_length  # 最后更新
```

### ⚠️ 单实例页面切换时必须重置 appBridge 瞬态状态

**问题**：NavigationView 单实例模式下，页面切换后 `appBridge` 的瞬态状态（如 `textId`）仍保留上一次的值，导致成绩提交到错误文本。

**修复**：在 `onActiveChanged` 中重置所有瞬态状态：
```qml
onActiveChanged: {
    if (active && appBridge) {
        appBridge.setTextTitle(appBridge.defaultTextTitle);
        appBridge.setTextId(0);  // 重置 textId，强制重新载文
    }
}
```

**原则**：`onActiveChanged` 重置所有与"当前载文"相关的状态。

**详细修改**：`RinUI/LOCAL_MODIFICATIONS.md` § **修改 3**（NavigationView 单实例重构）

### ⚠️ 领域模型不应承载 UI 路由概念

**问题**：`SessionStat`（领域模型）曾包含 `text_source_key` 字段，用来记录"这次打字来自哪个文本来源"。这个概念是 UI 路由层（ComboBox 选择来源）和数据管理层（服务端 TextSource 分组）的职责，不属于打字会话的业务属性。

**后果**：
- 成绩提交时携带了不必要的 `sourceKey` 参数
- 服务端需要 `findOrCreate` 逻辑来处理"文本不存在就创建"的复杂场景
- 概念混淆：source_key 被当成了成绩的核心属性

**正确做法**：
- 领域模型（SessionStat）只包含打字本身的属性：time, key_stroke_count, char_count, wrong_char_count
- 来源标识（source_key）是 UI 路由和数据管理的概念，不应进入领域层
- 成绩提交只需关联已存在的文本 ID（服务端主键），不需要来源信息

**原则**：领域模型 = 纯业务概念。UI 路由、数据分组等概念属于 Application/Presentation 层，不应污染领域模型。

**历史记录**：2026-04-13 架构重构中删除了 `SessionStat.text_source_key`，成绩提交简化为只传 `textId`。

### ⚠️ TextAdapter 所有文本加载必须走 Worker（禁止主线程同步加载）

**问题**：本地文本加载曾在主线程同步执行，导致页面切换时 UI 严重阻塞。

**原因**：本地文本来源（如 `builtin_demo`）有 `local_path`，旧代码的 `_load_from_local()` 除了读文件外，还调用 `_lookup_server_text_id()` 回查服务端获取 `text_id`。这个回查涉及同步 HTTP 请求（`fetch_text_by_client_id`），可能耗时数百毫秒。当默认来源是本地来源时，每次进入跟打页面都会在主线程触发这个同步网络请求，导致 UI 冻结。

**当前架构（两阶段异步）：**
1. **Worker 阶段**：`_load_from_local()` 只读文件，立即返回 text_id=None，载文即时显示
2. **Daemon thread 阶段**：TextAdapter 检测到 text_id=None 时，启动后台 daemon thread 调用 `gateway.lookup_text_id()` 异步回查；成功后通过 `localTextIdResolved` 信号 → Bridge.setTextId() 更新排行榜

**错误做法**：根据 `execution_mode` 决定走同步还是异步：
```python
# ❌ 错误：本地来源走同步路径，内部可能含同步 HTTP 请求
if plan.execution_mode == "sync":
    self._load_sync(plan)  # 主线程阻塞！
else:
    self._load_async(plan)
```

**正确做法**：所有文本加载统一走 Worker：
```python
# ✅ 正确：所有加载走后台 Worker，避免主线程阻塞
def requestLoadText(self, source_key: str) -> None:
    plan = self._load_text_usecase.plan_load(source_key)
    self._load_async(plan)  # 无论本地还是网络，都走 Worker
```

**原则**：任何可能涉及 I/O（文件、网络）的操作都不应在主线程同步执行，即使"理论上"是快速的本地操作，也可能隐含网络调用（如回查服务端 ID）。

**历史记录**：2026-04-16 发现并修复。默认来源 `builtin_demo` 是本地文件，`_lookup_server_text_id` 发起同步 HTTP 请求导致跟打页面切换时 UI 阻塞。2026-04-19 进一步拆分为两阶段：Worker 只读文件，HTTP 回查移至 daemon thread。修复 `QTimer.singleShot` lambda 在该 Qt 环境下静默失败的问题，改用 Qt 原生 QueuedConnection 跨线程信号。

### ⚠️ RinUI ContextMenu 的 height 不能用 enter transition 动画驱动

**问题**：RinUI 的 `ContextMenu`（ComboBox 的 popup）首次打开时会"展开一点又缩回去"。

**原因**：`enter` transition 中对 `height` 做动画，但首次打开时 ListView 尚未完成布局，`implicitHeight` 为 0，导致动画到 ~6px 后缩回。更致命的是 transition 会破坏 `height` 的属性绑定。

**正确做法**：移除 `enter` transition 中的 `height` 动画，改用 `Behavior on height`：
```qml
// ✅ 正确：Behavior on height 驱动展开
height: implicitHeight
Behavior on height {
    NumberAnimation { duration: Utils.animationSpeedMiddle; easing.type: Easing.OutQuint }
}
enter: Transition { /* 只动画 opacity，不动画 height */ }
```

**原则**：当属性值依赖异步计算结果时，不要用 `enter` transition 动画该属性。

**详细修改**：`RinUI/LOCAL_MODIFICATIONS.md` § **修改 1.1**（位置修复）+ § **修改 1.2**（PauseAnimation 修复）

### ⚠️ RinUI ComboBox 的 `onActivated` 信号不触发

**问题**：ComboBox 使用 `textRole`/`valueRole` 时，`onActivated` 信号不触发。

**原因**：RinUI 使用 Qt Quick Controls 2 的原生 ComboBox，内部机制可能干扰信号转发。

**正确做法**：改用 `onCurrentIndexChanged`，需要去重时加守卫：
```qml
onCurrentIndexChanged: {
    if (currentIndex >= 0 && currentIndex < model.count) {
        var val = model.get(currentIndex).value;
        if (val !== currentVal) { currentVal = val; doSomething(); }
    }
}
```

**详细修改**：`RinUI/LOCAL_MODIFICATIONS.md` § **修改 1.1**（ContextMenu 位置修复，同文件）

### ⚠️ 清空 UpperPane 文本前必须先重置光标位置

**问题**：分片载文模式下，打完一个片段后 `onTypingEnded` 直接设置 `upperPane.text = ""` 清空显示区，触发 `QTextCursor::setPosition: Position 'X' out of range` 警告。

**原因**：清空 `upperPane.text` 时，Qt 内部的 QTextCursor 仍停留在旧位置（如片段末尾的位置 9）。文档被清空后（characterCount 变为 1），Qt 尝试将光标定位到旧位置，导致越界。该警告在每次打完片段后稳定复现。

**正确做法**：在清空文本前先将光标重置到起始位置：
```qml
// ✅ 正确：先重置光标，再清空文本
upperPane.setCursorAndScroll(0, false);
upperPane.text = "";
```

```qml
// ❌ 错误：直接清空文本，Qt 内部光标仍在旧位置
upperPane.text = "";
```

**补充防护**：`_color_text` 方法中增加了 `begin_pos + n > doc_len` 的边界检查，防止 `movePosition` 越界。即使有残留 IME 事件穿过 `is_read_only` 守卫，也不会触发 setPosition 警告。

**原则**：在 QML 中程序化替换/清空 TextEdit 的文本时，若光标不在位置 0，应先重置光标位置再修改文本内容，避免 Qt 内部光标定位越界。

**历史记录**：2026-04-27，分片载文模式修复。此问题在每次打完片段后稳定复现，但因不影响功能只产生警告日志，长期未被发现。

### ⚠️ 分片达标次数在片段切换时必须归零

**问题**：分片载文模式下，离开片段后再回来时，达标次数仍然是之前累计的值，导致一次达标就触发自动推进。

**正确做法**：片段切换时重置目标片段的达标次数：
```python
# ✅ 正确：loadNextSlice / loadPrevSlice / loadRandomSlice 中
self._typing_adapter.reset_slice_pass_count(next_idx)
self._typing_adapter.set_slice_index(next_idx)
```

**不应重置的场景**：同一片段重打（`handleSliceRetype`）时保留达标次数。

**原则**：达标次数的生命周期是"一次片段访问"。进入时从 0 开始，片段内重打累加，离开时归零。

**详细修改**：`RinUI/LOCAL_MODIFICATIONS.md` § **修改 3**（NavigationView 单实例，含片段管理）
