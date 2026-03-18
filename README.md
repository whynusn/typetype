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
- 异步加载：`QThreadPool + LoadTextWorker`

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
  --noinclude-dlls=webengine \
  --include-data-dir=src/qml=src/qml \
  --include-data-dir=resources/texts=resources/texts \
  --include-data-files=resources/images/TypeTypeLogo.png=resources/images/TypeTypeLogo.png \
  --include-data-files=resources/fonts/HarmonyOS_Sans_SC_Regular.ttf=resources/fonts/HarmonyOS_Sans_SC_Regular.ttf \
  --include-data-files=resources/fonts/LXGWWenKai-Regular.ttf=resources/fonts/LXGWWenKai-Regular.ttf
```

Windows 建议追加：`--assume-yes-for-downloads`。

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
│   │   │   └── usecases/
│   │   ├── config/
│   │   ├── core/
│   │   ├── domain/          # 领域服务
│   │   ├── integration/     # 内外集成
│   │   ├── models/
│   │   ├── security/
│   │   ├── typing/
│   │   ├── utils/
│   │   ├── workers/
│   │   └── text_properties.py
│   └── qml/
└── tests/
```

## 架构说明

### 分层概述

```
┌─────────────────────────────────────────────────────┐
│                    QML 层                           │
│   (UI 组件通过 appBridge 与后端通信)                 │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│              Bridge (QML 通信适配层)                  │
│   - 属性代理（loggedin, userNickname, typeSpeed 等） │
│   - 信号转发（Service → QML）                        │
│   - Slot 入口（QML → Service）                       │
└─────────┬───────────────────────────┬───────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────┐   ┌─────────────────────────────┐
│   Domain Services   │   │      Application Layer     │
│                    │   │                             │
│  - TypingService   │   │  - TextUseCase             │
│  - TextLoadService │   │  - ScoreUseCase             │
│  - AuthService     │   │                             │
└─────────────────────┘   └──────────────┬──────────────┘
                                         │
                                         ▼
                              ┌─────────────────────────────┐
                              │      Ports (接口定义)        │
                              │                             │
                              │  - TextFetcher              │
                              │  - LocalTextLoader          │
                              │  - ClipboardReader/Writer   │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │   Integration (实现)        │
                              │                             │
                              │  - SaiWenService           │
                              │  - QtLocalTextLoader       │
                              │  - QtClipboard             │
                              └─────────────────────────────┘
```

### 职责说明

| 层次 | 职责 | 示例 |
|------|------|------|
| **Bridge** | QML 通信适配层，仅做属性代理和信号转发 | `appBridge.typeSpeed` |
| **Domain Service** | 领域逻辑 + 状态管理 | `TypingService` 打字统计 |
| **UseCase** | 业务流程编排 + 异常转换 | `TextUseCase.load_text()` |
| **Port** | 接口定义（抽象依赖） | `TextFetcher` |
| **Integration** | 接口实现（具体细节） | `SaiWenService` |

### 依赖注入

`main.py` 负责所有对象的创建和注入：

```python
typing_service = TypingService(score_usecase=score_usecase)
text_load_service = TextLoadService(text_usecase=text_usecase, runtime_config=runtime_config)
auth_service = AuthService(...)
bridge = Bridge(
    typing_service=typing_service,
    text_load_service=text_load_service,
    auth_service=auth_service,
    runtime_config=runtime_config,
)
```

### 各 Service 职责

- **TypingService**：打字统计（ScoreData、计时器、键数累积、文本上色）
- **TextLoadService**：文本加载（网络/本地/剪贴板路由、Worker 线程管理）
- **AuthService**：登录认证（login/logout、token 刷新、状态持久化）
- **RuntimeConfig**：管理文本来源列表和默认来源

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
2. 新增 `SpringBootTextService`（实现 `TextFetcher` 协议）。
3. `main.py` 切换注入：`TextUseCase(text_fetcher=springboot_service, ...)`。
4. 保留 `SaiWenService` 作为回退来源，逐步迁移。

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
