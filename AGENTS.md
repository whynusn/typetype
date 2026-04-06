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
│   └── usecases/      # 业务编排：LoadTextUseCase（仅此一个有编排价值的）
├── ports/             # 协议定义（独立顶层）：TextProvider, LocalTextLoader 等
├── config/            # RuntimeConfig
├── domain/
│   └── services/      # 纯业务逻辑（TypingService, AuthService, CharStatsService）
├── infrastructure/    # ApiClient 与网络异常模型
├── integration/       # 内外集成（RemoteTextProvider, SqliteCharStatsRepository）
├── models/            # 领域模型（SessionStat, CharStat, DTO）
├── presentation/
│   ├── adapters/      # Qt 适配层（TypingAdapter, TextAdapter）
│   └── bridge.py      # Bridge（appBridge）
├── security/          # 加密与安全存储
├── utils/             # 工具类（Logger）
└── workers/           # 后台任务（BaseWorker, TextLoadWorker, SessionStatWorker）
```

RinUI/                   # 第三方 QML 框架（本地 vendored，不修改）

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
- 文本加载支持 `network` 与 `local` 两类来源。
- UI 框架使用 RinUI（vendored），提供主题、组件和暗色模式支持。
- UI 字体由 `main.py` 中 `app.setFont()` 全局设置，QML 层不再传递字体属性。
- `pyproject.toml` 中 `[tool.ruff] exclude = ["RinUI"]` 排除第三方代码的 lint 检查。

### 各层职责

| 层 | 组件 | 职责 |
|------|------|------|
| **Domain Services** | TypingService | 打字统计纯逻辑（SessionStat 状态、键数累积） |
| | AuthService | 登录认证（login/logout、token 验证与刷新） |
| | CharStatsService | 字符维度统计（缓存、持久化、薄弱字查询） |
| **Application** | LoadTextUseCase | 文本加载路由 + 业务验证（异常上浮到 BaseWorker） |
| | GlobalExceptionHandler | 网络异常 → 用户友好消息集中映射 |
| **Gateways** | TextSourceGateway | Port 适配 + 配置查询 |
| | ScoreGateway | DTO 转换 + 剪贴板操作 |
| **Workers** | BaseWorker | 统一捕获后台任务异常，调用 GlobalExceptionHandler |
| **Presentation** | Bridge | QML 通信适配层：属性代理、信号转发、Slot 入口 |
| | TypingAdapter | Qt 适配（计时器、文本着色、信号发射） |
| | TextAdapter | Qt 适配（异步 Worker、信号发射） |

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
text_gateway = TextGateway(
    runtime_config=runtime_config,
    text_fetchers={"sai_wen": sai_wen_text_fetcher},
    clipboard=clipboard,
    local_text_loader=local_text_loader,
)
score_gateway = ScoreGateway(clipboard=clipboard)

# UseCases
load_text_usecase = LoadTextUseCase(gateway=text_gateway)

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
typing_adapter = TypingAdapter(typing_service=typing_service, score_gateway=score_gateway)
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

- `GET /api/v1/texts/random?sourceKey={key}`
- `GET /api/v1/text-sources`
- `POST /api/v1/scores`

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
