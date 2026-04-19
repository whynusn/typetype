# typetype 项目开发指南

## 1. 开发环境与命令

### 开发环境

- Python 3.12+（见 `.python-version`）
- 包管理器：`uv`（建议 0.9.26+）

### 启动

```bash
uv sync
uv run python main.py
```

### 测试与检查

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### 打包（Nuitka）

```bash
uv run python -m ensurepip --upgrade
uv pip install --upgrade nuitka --index-url https://pypi.org/simple
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
  --include-data-files=resources/fonts/HarmonyOS_Sans_SC_Regular-subset.ttf=resources/fonts/HarmonyOS_Sans_SC_Regular-subset.ttf \
  --include-data-files=resources/fonts/LXGWWenKai-Regular-subset.ttf=resources/fonts/LXGWWenKai-Regular-subset.ttf
```

Windows 建议追加：`--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*`。

### 字体裁剪说明

项目使用了裁剪后的字体文件以减小打包体积和运行时内存占用：

| 字体 | 原始大小 | 裁剪后大小 | 减少比例 |
|------|----------|------------|----------|
| HarmonyOS Sans SC Regular | 8.2 MB | 504 KB | ~94% |
| LXGW WenKai Regular | 25.4 MB | 880 KB | ~97% |

裁剪后的字体文件（`*-subset.ttf`）仅包含项目实际使用的中文字符，打包时应使用这些裁剪版本而非原始字体文件。

## 2. 当前架构（以代码为准）

> 完整的架构文档请见 [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)，本文档是补充速查和陷阱案例。

```
src/backend/
├── application/
│   ├── exception_handler.py  # 全局异常处理（网络异常 → 用户友好消息）
│   ├── gateways/      # Port 适配（TextSourceGateway, ScoreGateway）
│   │   ├── score_gateway.py
│   │   ├── text_source_gateway.py
│   │   └── leaderboard_gateway.py   # 排行榜数据获取网关（Port 适配）
│   └── usecases/      # 业务编排：LoadTextUseCase（仅此一个有编排价值的）
│       └── load_text_usecase.py
├── ports/             # 协议定义（独立顶层）：TextProvider, LocalTextLoader 等
│   ├── auth_provider.py
│   ├── char_stats_repository.py
│   ├── clipboard.py
│   ├── local_text_loader.py
│   ├── score_submitter.py
│   ├── text_provider.py
│   ├── text_uploader.py
│   ├── async_executor.py
│   └── leaderboard_provider.py
├── config/            # 运行时 JSON 配置文件
│   ├── runtime_config.py
│   └── text_source_config.py
├── domain/
│   └── services/      # 纯业务逻辑（TypingService, AuthService, CharStatsService）
│       ├── auth_service.py
│       ├── char_stats_service.py
│       └── typing_service.py
├── infrastructure/    # ApiClient 与网络异常模型
│   ├── api_client.py
│   └── network_errors.py
├── integration/       # 内外集成（RemoteTextProvider, SqliteCharStatsRepository）
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
│   └── leaderboard_fetcher.py    # LeaderboardProvider 实现
├── models/
│   ├── dto/
│   │   ├── auth_dto.py
│   │   ├── fetched_text.py
│   │   ├── score_dto.py
│   │   └── text_catalog_item.py
│   └── entity/        # 领域模型（SessionStat, CharStat）
│       ├── char_stat.py
│       └── session_stat.py
├── presentation/
│   ├── adapters/      # Qt 适配层（TypingAdapter, TextAdapter）
│   │   ├── typing_adapter.py
│   │   ├── text_adapter.py
│   │   ├── auth_adapter.py
│   │   ├── char_stats_adapter.py
│   │   ├── leaderboard_adapter.py
│   │   └── upload_text_adapter.py
│   └── bridge.py      # Bridge（appBridge）
├── security/          # 加密与安全存储
│   ├── crypt.py
│   └── secure_storage.py
├── utils/             # 工具类（Logger, text_id）
│   ├── logger.py
│   └── text_id.py
└── workers/           # 后台任务（BaseWorker, TextLoadWorker 等）
    ├── base_worker.py
    ├── catalog_worker.py
    ├── leaderboard_worker.py
    ├── text_load_worker.py
    ├── text_list_worker.py
    └── weak_chars_query_worker.py
```

RinUI/                   # 第三方 QML 框架（本地 vendored，少量必要修改，见 docs/ARCHITECTURE.md）

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    QML 层                              │
│           (通过 appBridge 与后端通信)                    │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                  Presentation Layer                     │
│                 (Bridge + Adapters)                    │
│  Bridge: appBridge，属性代理/信号转发/Slot 入口          │
│  Adapters: TypingAdapter, TextAdapter                   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                     Application Layer                   │
│        UseCases: LoadTextUseCase（路由+业务验证）         │
│        Gateways: TextSourceGateway, ScoreGateway        │
│        ExceptionHandler: GlobalExceptionHandler        │
└─────────┬───────────────────────────┬───────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────┐   ┌───────────────────────────┐
│      Domain Services    │   │          Ports            │
│ (纯业务逻辑，无 Qt 依赖)  │   │   (接口协议 / 抽象依赖)    │
│ Typing/Auth/CharStats   │   │ TextFetcher, Clipboard... │
└─────────┬───────────────┘   └───────────┬───────────────┘
           │                               │
           └──────────────┬────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Integration / Infrastructure           │
│   SaiWenTextFetcher, SqliteRepo, ApiClient, QtLoader   │
└─────────────────────────────────────────────────────────┘
```

### 关键点

- 依赖注入在 `main.py` 完成，不再使用全局 registry。
- QML 通过 `appBridge` 与后端交互。
- **Domain Services 是纯业务逻辑**，无 Qt 依赖，易于测试。
- **Presentation Layer = Bridge + Adapters**，统一封装 QML 与 Qt 交互细节。
- **Gateways 封装 Port 适配**（不含异常转换）。
- **GlobalExceptionHandler 集中处理异常语义**（网络异常 → 用户友好消息），类似 Spring Boot 的 `@ControllerAdvice`。
- **BaseWorker 统一捕获后台任务异常**，调用 GlobalExceptionHandler 转换后发射 `failed` 信号。
- **UseCases 编排业务流程**（路由 + 业务验证），异常上浮由 BaseWorker 统一处理。
- 文本加载支持 `network` 与 `local` 两类来源，**所有加载统一走后台 Worker**，避免主线程同步 I/O 阻塞 UI。
- **FluentPage 不使用 `layer.effect`**（避免 GPU 离屏渲染阻塞页面切换），圆角裁切由 `Flickable.clip` 和 `appLayer` 背景配合实现。
- UI 框架使用 RinUI（vendored），提供主题、组件和暗色模式支持。
- UI 字体由 `main.py` 中 `app.setFont()` 全局设置，QML 层不再传递字体属性。
- `pyproject.toml` 中 `[tool.ruff] exclude = ["RinUI"]` 排除第三方代码的 lint 检查。

### 各层职责

| 层 | 组件 | 职责 |
|------|------|------|
| **Domain Services** | TypingService | 打字统计纯逻辑（SessionStat 状态、键数累积） |
| | AuthService | 登录认证（login/logout、token 验证与刷新） |
| | CharStatsService | 字符维度统计（缓存、持久化、薄弱字查询、自定义排序） |
| **Application** | LoadTextUseCase | 文本加载编排 + 业务验证（异常上浮到 BaseWorker） |
| | GlobalExceptionHandler | 网络异常 → 用户友好消息集中映射 |
| **Gateways** | TextSourceGateway | Port 适配 + 配置查询 |
| | ScoreGateway | DTO 转换 + 剪贴板操作 |
| | LeaderboardGateway | 排行榜 Port 适配 + 数据代理 |
| **Workers** | BaseWorker | 统一捕获后台任务异常，调用 GlobalExceptionHandler |
| | LeaderboardWorker | 排行榜后台加载 |
| | TextListWorker | 文本列表后台加载 |
| | WeakCharsQueryWorker | 弱字符后台查询 |
| **Presentation** | Bridge | QML 通信适配层：属性代理、信号转发、Slot 入口 |
| | TypingAdapter | Qt 适配（计时器、文本着色、信号发射） |
| | TextAdapter | Qt 适配（所有加载走 Worker、信号发射、UI 配置展示） |
| | LeaderboardAdapter | 排行榜 Qt 适配（异步 Worker、信号管理） |
| | UploadTextAdapter | 文本上传 Qt 适配（本地写入 + 云端上传） |

### 薄弱字排序功能

薄弱字（Weak Chars）支持自定义排序模式，全链路传递排序参数：

**数据流**：WeakCharsPage.qml → Bridge → CharStatsAdapter → WeakCharsQueryWorker → CharStatsService → CharStatsRepository

**排序模式**（`CharStatsRepository.get_chars_by_sort`）：

| sort_mode | 说明 |
|-----------|------|
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
- `TypingService/AuthService/CharStatsService`：纯业务规则，无 Qt 依赖

**扩展异常**：在 `exception_handler.py` 的 `_EXCEPTION_MESSAGE_MAP` 中添加新映射即可，无需修改 UseCase。

### Bridge 职责（薄适配层）

- **属性代理**：透传各 Adapter 的只读属性到 QML（`loggedin`, `typeSpeed`, `textLoading` 等）
- **信号转发**：Adapter 发射的信号转发到 QML 层
- **Slot 入口**：QML 调用请求转发到对应 Adapter

```python
# main.py 中的依赖注入示例
# Infrastructure
api_client = ApiClient(timeout=runtime_config.api_timeout)
sai_wen_text_fetcher = SaiWenTextFetcher(api_client=api_client)
local_text_loader = QtLocalTextLoader()
async_executor = QtAsyncExecutor()

# Gateways
text_source_gateway = TextSourceGateway(
    runtime_config=runtime_config,
    text_provider=sai_wen_text_fetcher,
    local_text_loader=local_text_loader,
)
score_gateway = ScoreGateway(clipboard=clipboard)

# UseCases
load_text_usecase = LoadTextUseCase(
    text_gateway=text_source_gateway,
    clipboard_reader=clipboard,
)

# Domain Services
char_stats_service = CharStatsService(repo=char_stats_repo, async_executor=async_executor)
typing_service = TypingService(char_stats_service=char_stats_service)

auth_provider = ApiClientAuthProvider(
    api_client=api_client,
    login_url=runtime_config.login_api_url,
    validate_url=runtime_config.validate_api_url,
    refresh_url=runtime_config.refresh_api_url,
)
auth_service = AuthService(auth_provider=auth_provider)

# Adapters
typing_adapter = TypingAdapter(
    typing_service=typing_service,
    score_gateway=score_gateway,
    score_submitter=score_submitter,
)
text_adapter = TextAdapter(text_gateway=text_gateway, load_text_usecase=load_text_usecase)
auth_adapter = AuthAdapter(auth_service=auth_service)
char_stats_adapter = CharStatsAdapter(char_stats_service=char_stats_service)

# Bridge
bridge = Bridge(
    typing_adapter=typing_adapter,
    text_adapter=text_adapter,
    auth_adapter=auth_adapter,
    char_stats_adapter=char_stats_adapter,
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

## 4. 测试策略

- 优先覆盖用例层与核心逻辑，不依赖真实 UI
- 对网络错误、超时、解析异常必须有测试（由 GlobalExceptionHandler 统一转换）
- 新增文本来源时，需同时补充：
  - `LoadTextUseCase` 测试（业务验证、路由分支）
  - `GlobalExceptionHandler` 测试（新异常类型 → 用户消息映射）
  - 对应 service/integration 测试

## 5. Spring Boot 服务接入规范（后续）

当前项目尚未正式接入 Spring Boot。接入时遵循以下规范。

### 接入原则

- 用例层只依赖 `TextFetcher` 协议，不直接依赖 HTTP 细节。
- Spring Boot 作为新的 integration/service 实现注入，不破坏现有调用链。

### 推荐接口（v1）

- `GET /api/v1/texts/latest/{sourceKey}` — 获取指定来源的最新文本
- `GET /api/v1/texts/catalog` — 获取所有可用文本来源
- `POST /api/v1/scores` — 提交成绩（只发 textId，不发 sourceKey/content）
- `GET /api/v1/texts/{textId}/leaderboard` — 获取文本排行榜

### 客户端实现建议

1. 新建 `SpringBootTextService`（实现 `TextFetcher`）。
2. 复用 `ApiClient`，统一异常映射到 `network_errors.py`。
3. 在 `RuntimeConfig.text_sources` 添加 springboot 来源。
4. 在 `main.py` 按环境切换注入目标 service。

### 配置建议

后续建议新增环境变量支持：

- `TYPETYPE_TEXT_API_BASE_URL`
- `TYPETYPE_SCORE_API_BASE_URL`
- `TYPETYPE_API_TIMEOUT`

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

### ⚠️ StackView 页面切换时必须重置 appBridge 瞬态状态

**问题**：StackView 每次导航都会 `createObject` 创建新的 TypingPage 实例，但 `appBridge` 是 Python 单例，页面切换后其内部状态（如 `textId`）仍保留上一次的值。

**场景**：
1. 用户载文（极速杯 textId=49）→ 打到一半
2. 切到排行榜页面 → 再切回打字页面
3. 新 TypingPage 实例创建，文本区为空，ComboBox 显示默认来源
4. 但 `appBridge.textId` 仍然是 49
5. 用户直接开始打字 → 完成后提交成绩 → 成绩关联到旧的 textId=49，但打的是新内容

**修复**：在 `StackView.onActivating` 中重置所有瞬态状态：
```qml
StackView.onActivating: {
    if (appBridge) {
        appBridge.setTextTitle(appBridge.defaultTextTitle);
        appBridge.setTextId(0);  // 重置 textId，强制用户重新载文
    }
}
```

**原则**：`StackView.onActivating` 应该重置所有与"当前载文"相关的状态，确保用户每次回到页面都是一致的初始状态。如果某个状态是从外部单例读取的，必须显式重置。

**历史记录**：此问题在 2026-04-13 的架构重构（source_key / 成绩提交简化）中发现并修复。

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

**原因**：`enter` transition 中的 `NumberAnimation` 将 `height` 从 46 动画到 `contextMenu.implicitHeight`。但首次打开时，ListView 的 model 只在 `popup.visible` 变为 true 后才设置（`model: control.popup.visible ? control.delegateModel : null`），delegate 尚未实例化，`contentHeight` 为 0，导致 `implicitHeight` ≈ 6。动画目标值错误，popup 从 46 缩到 ~6。更致命的是，transition 动画会破坏 `height` 的属性绑定，后续 `contentHeight` 更新无法传递到 `height`，导致 popup 永久卡在错误高度。

**错误做法**：在 `enter` transition 中对 `height` 做动画：
```qml
// ❌ 错误：enter transition 动画 height
enter: Transition {
    SequentialAnimation {
        PauseAnimation { duration: 16 }
        NumberAnimation {
            target: contextMenu
            property: "height"
            from: 46
            to: contextMenu.implicitHeight  // 首次打开时 ≈ 6，导致缩回
        }
    }
}
```

**正确做法**：移除 `enter` transition 中的 `height` 动画，改用 `Behavior on height` 驱动展开。`Behavior` 不破坏属性绑定，当 `implicitHeight` 因 `contentHeight` 变化而更新时，`height` 自然跟随，`Behavior` 提供平滑过渡：
```qml
// ✅ 正确：Behavior on height 驱动展开
height: implicitHeight
Behavior on height {
    NumberAnimation {
        duration: Utils.animationSpeedMiddle
        easing.type: Easing.OutQuint
    }
}
enter: Transition {
    // 只动画 opacity，不动画 height
}
```

**原则**：当属性值依赖异步计算结果（如 `ListView.contentHeight`）时，不要在 `enter` transition 中对该属性做动画——transition 的 `to` 值在启动时就被求值，此时异步数据可能尚未就绪。应使用 `Behavior` 让属性绑定自然驱动动画。

**历史记录**：2026-04-16 发现并修复。

### ⚠️ RinUI ComboBox 的 `onActivated` 信号不触发

**问题**：在 RinUI 框架下，ComboBox 使用 `textRole`/`valueRole` 绑定 ListModel 时，`onActivated` 信号处理函数不被执行。用户点击下拉选项后，回调不触发。

**原因**：RinUI 没有自己的 ComboBox 组件，使用 Qt Quick Controls 2 的原生 ComboBox。但 RinUI 的某些内部机制可能干扰了 `onActivated` 信号的转发。SettingsPage 已使用 `onCurrentIndexChanged` 而非 `onActivated`。

**正确做法**：改用 `onCurrentIndexChanged`。排序等需要去重的场景加守卫：
```qml
onCurrentIndexChanged: {
    if (currentIndex >= 0 && currentIndex < model.count) {
        var val = model.get(currentIndex).value;
        if (val !== currentVal) {
            currentVal = val;
            doSomething();
        }
    }
}
```

**历史记录**：2026-04-19，薄弱字排序功能和文本排行页面修复。
