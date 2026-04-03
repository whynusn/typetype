# Typetype

一个基于 PySide6 + QML 的跨平台打字练习工具，当前支持本地文本与网络文本载文，提供实时速度、准确率、击键等统计。

## 当前状态（2026-03）

- 平台：Linux / Windows
- UI：QML（`src/qml`）
- 后端：Python（`src/backend`）
- 架构：用例层 + 端口协议（Ports）+ 集成实现（Integration）
- 文本来源：
  - 网络：极速杯（`jisubei`）
  - 本地内置：示例、前五百、中五百、后五百、打词必备单字
- 异步加载：`QThreadPool + TextLoadWorker`

## 功能特性

- 实时指标：速度、准确率、总时间、击键数
- 打字结束统计弹窗
- 历史记录维护
- 本地文本与网络文本统一加载入口
- Linux 全局键盘监听（Wayland/X11 区分处理）
- 网络错误分型与用户提示（超时/请求失败/响应解析失败/状态码异常）

## 快速开始

```bash
uv sync
uv run python main.py
```

## 开发命令

```bash
# 测试
uv run pytest

# 代码检查
uv run ruff check .
uv run ruff format --check .

# 自动格式化
uv run ruff format .
```

## 日志开关

默认只输出 warning 及以上日志。可通过环境变量开启调试输出：

- `TYPETYPE_DEBUG=1` 启用 debug 级日志
- `TYPETYPE_LOG_LEVEL=info|warning|error|none` 设置日志级别

## 打包（Nuitka）

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

## 项目结构（核心）

```text
typetype/
├── main.py
├── RinUI/               # 第三方 QML 框架（vendored）
├── resources/
│   ├── fonts/
│   ├── images/
│   └── texts/
├── src/
│   ├── backend/
│   │   ├── application/
│   │   │   ├── ports/
│   │   │   ├── gateways/
│   │   │   └── usecases/
│   │   ├── config/
│   │   ├── domain/          # 领域服务
│   │   ├── infrastructure/  # 网络客户端与异常模型
│   │   ├── integration/     # 内外集成
│   │   ├── models/
│   │   ├── presentation/
│   │   │   ├── adapters/
│   │   │   └── bridge.py
│   │   ├── security/
│   │   ├── utils/
│   │   ├── workers/
│   └── qml/
└── tests/
```

## 架构说明

### 分层概述

```
┌─────────────────────────────────────────────────────────┐
│                    QML 层                               │
│           (通过 appBridge 与后端通信)                   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                  Presentation Layer                     │
│                 (Bridge + Adapters)                     │
│  Bridge: appBridge，属性代理/信号转发/Slot 入口         │
│  Adapters: TypingAdapter, TextAdapter, AuthAdapter,    │
│            CharStatsAdapter                            │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                     Application Layer                   │
│              UseCases: LoadTextUseCase                  │
│   Gateways: TextSourceGateway, ScoreGateway             │
└─────────┬───────────────────────────┬───────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────────┐   ┌───────────────────────────┐
│      Domain Services    │   │          Ports            │
│ (纯业务逻辑，无 Qt 依赖)│   │   (接口协议 / 抽象依赖)   │
│  Typing/Auth/CharStats  │   │ TextFetcher, Clipboard... │
└─────────┬───────────────┘   └───────────┬───────────────┘
          │                               │
          └──────────────┬────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Integration / Infrastructure               │
│ RemoteTextProvider, SqliteRepo, ApiClient, QtLoader     │
└─────────────────────────────────────────────────────────┘
```

### 职责说明

| 层次 | 职责 | 示例 |
|------|------|------|
| **Presentation（Bridge + Adapters）** | UI 适配层；Bridge 负责 QML 入口与转发，Adapters 封装 Qt 细节 | `appBridge` / `TypingAdapter` / `TextAdapter` |
| **Application (UseCases)** | 业务流程编排、结果封装 | `LoadTextUseCase.load()` |
| **Application (Gateways)** | Port 适配、配置查询、DTO/剪贴板转换 | `TextSourceGateway` / `ScoreGateway` |
| **Domain Services** | 纯业务逻辑与状态计算（无 Qt 依赖） | `TypingService` / `CharStatsService` / `AuthService` |
| **Ports** | 协议定义（抽象依赖） | `TextProvider` / `LocalTextLoader` / `CharStatsRepository` |
| **Integration** | 端口实现与外部系统接入 | `RemoteTextProvider` / `SqliteCharStatsRepository` |

### 依赖注入

`main.py` 负责所有对象的创建和注入：

```python
typing_service = TypingService(char_stats_service=char_stats_service)
load_text_usecase = LoadTextUseCase(
    text_gateway=text_gateway,
    clipboard_reader=clipboard_reader,
)
auth_service = AuthService(...)
char_stats_service = CharStatsService(repository=char_stats_repo)
auth_adapter = AuthAdapter(auth_service=auth_service)
char_stats_adapter = CharStatsAdapter(char_stats_service=char_stats_service)
bridge = Bridge(
    typing_adapter=typing_adapter,
    text_adapter=text_adapter,
    auth_adapter=auth_adapter,
    char_stats_adapter=char_stats_adapter,
)
```

### 核心组件职责

- **TypingService**：打字统计状态与计数逻辑（无 Qt 依赖）
- **LoadTextUseCase**：文本加载入口，负责结果封装并协调 `TextSourceGateway` / `ClipboardReader`
- **AuthService**：登录认证（login/logout、token 刷新、状态持久化）
- **CharStatsService**：字符维度统计（缓存、异步持久化、薄弱字查询）
- **TextSourceGateway**：根据 `RuntimeConfig` 做来源查询与本地/网络路由
- **RuntimeConfig**：管理文本来源列表和默认来源；在 `TextAdapter` 中仅用于 UI 配置展示

### 文本加载闭口

- 文本加载主入口现在是 `LoadTextUseCase.plan_load() -> LoadTextUseCase.load() -> TextSourceGateway`。
- 同步/异步执行策略已经由 `Application` 输出，`TextAdapter` 只负责执行同步调用或入队 Worker。
- `TextAdapter` 不再通过 `RuntimeConfig` 做行为判断；`RuntimeConfig` 仅保留 UI 来源列表/默认来源展示用途。
- 详细边界规则见 `docs/developer-architecture-handbook.md`。

## Spring Boot 服务接入规划

当前项目尚未接入 Spring Boot，下面是推荐落地方案。

### 1. 接入目标

- 将“网络载文”从第三方接口迁移到自建 Spring Boot 服务。
- 可选：把成绩上报、历史记录同步也迁移到服务端。

### 2. 推荐接口约定（v1）

- `GET /api/v1/texts/random?sourceKey={key}`
  - 200：`{"text":"...","title":"...","sourceKey":"..."}`
- `GET /api/v1/text-sources`
  - 200：`[{"key":"cet4","label":"四级词库","type":"remote"}]`
- `POST /api/v1/scores`
  - body：`{"speed":123,"accuracyRate":98.7,...}`
  - 201：`{"id":"..."}`

### 3. Python 端改造建议

1. 在 `RuntimeConfig.text_sources` 增加 `springboot` 来源（`type=network`，URL 指向 Spring Boot）。
2. 新增 `SpringBootTextFetcher`（实现 `TextFetcher` 协议）。
3. `main.py` 注册多个 TextFetcher：`TextGateway(text_fetchers={"sai_wen": sai_wen, "springboot": springboot}, ...)`。
4. 用户可在 UI 中选择使用哪个来源（通过 `source_id` 关联 `fetcher_id`）。

**多个 TextFetcher 可以共存**，用户根据需要选择不同的来源。

### 4. 错误处理约定

- 服务端 4xx/5xx：映射为 `NetworkHttpStatusError`
- 超时：`NetworkTimeoutError`
- 非 JSON 响应：`NetworkDecodeError`

### 5. 配置建议

建议后续在 `RuntimeConfig` 支持环境变量覆盖，例如：

- `TYPETYPE_TEXT_API_BASE_URL`
- `TYPETYPE_SCORE_API_BASE_URL`
- `TYPETYPE_API_TIMEOUT`

## Linux 权限说明

Wayland 下启用全局键盘监听通常需要：

```bash
sudo usermod -aG input $USER
```

重新登录后生效。若未授权，应用会进行降级处理。

## 许可证

MIT
