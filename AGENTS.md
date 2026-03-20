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

## 2. 当前架构（以代码为准）

```
src/backend/
├── application/
│   ├── ports/       # 协议：Clipboard/TextFetcher/LocalTextLoader
│   └── usecases/    # 业务编排：TextUseCase/ScoreUseCase
├── config/          # RuntimeConfig
├── core/            # ApiClient 与网络异常模型
├── domain/          # 领域服务
│   ├── auth_service.py      # 登录认证
│   ├── text_load_service.py # 文本加载
│   └── typing_service.py    # 打字统计
├── integration/     # 内外集成
│   ├── global_key_listener.py   # 全局键盘监听
│   ├── local_text_loader.py     # 本地文本加载
│   ├── sai_wen_service.py       # 第三方网络文本服务
│   └── system_identifier.py     # 系统识别
├── models/          # 数据传输对象（ScoreDTO 等）
├── security/        # 加密相关
├── typing/          # 打字数据模型
├── utils/           # 日志等工具
├── workers/         # 后台任务（避免阻塞 UI）
└── bridge.py  # Bridge（appBridge）

RinUI/                   # 第三方 QML 框架（本地 vendored，不修改）
```

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    QML 层                              │
│           (通过 appBridge 与后端通信)                    │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              Bridge (QML 通信适配层)                       │
│   仅负责：属性代理、信号转发、Slot 入口                    │
└─────────┬───────────────────────────┬───────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────┐   ┌───────────────────────────────┐
│   Domain Services   │   │      Application Layer       │
│                     │   │                               │
│  - TypingService   │   │  - TextUseCase               │
│  - TextLoadService │   │  - ScoreUseCase               │
│  - AuthService     │   │                               │
└─────────────────────┘   └───────────────┬───────────────┘
                                            │
                                            ▼
                              ┌───────────────────────────────┐
                              │      Ports (接口定义)          │
                              │  - TextFetcher                │
                              │  - LocalTextLoader            │
                              │  - ClipboardReader/Writer     │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │   Integration (实现)          │
                              │  - SaiWenService             │
                              │  - QtLocalTextLoader          │
                              │  - QtClipboard                │
                              └───────────────────────────────┘
```

### 关键点

- 依赖注入在 `main.py` 完成，不再使用全局 registry。
- QML 通过 `appBridge` 与后端交互。
- 文本加载支持 `network` 与 `local` 两类来源。
- UI 框架使用 RinUI（vendored），提供主题、组件和暗色模式支持。
- UI 字体由 `main.py` 中 `app.setFont()` 全局设置，QML 层不再传递字体属性。
- `pyproject.toml` 中 `[tool.ruff] exclude = ["RinUI"]` 排除第三方代码的 lint 检查。

### 各 Service 职责

| Service | 职责 |
|---------|------|
| **TypingService** | 打字统计（ScoreData 状态、计时器、键数累积、文本上色、历史记录构建） |
| **TextLoadService** | 文本加载（来源路由、网络/本地/剪贴板加载、Worker 线程管理） |
| **AuthService** | 登录认证（login/logout、token 验证与刷新、状态持久化） |
| **CharStatsService** | 字符维度统计（缓存、异步持久化、薄弱字查询） |
| **SaiWenService** | 第三方网络文本获取（实现 TextFetcher 协议） |

### Bridge 职责（薄适配层）

- **属性代理**：透传各 Service 的只读属性到 QML（`loggedin`, `typeSpeed`, `textLoading` 等）
- **信号转发**：Service 发射的信号转发到 QML 层
- **Slot 入口**：QML 调用请求转发到对应 Service

```python
# main.py 中的依赖注入示例
typing_service = TypingService(score_usecase=score_usecase)
text_load_service = TextLoadService(text_usecase=text_usecase, runtime_config=runtime_config)
auth_service = AuthService(api_client=api_client, ...)
char_stats_service = CharStatsService(repo=char_stats_repo)
bridge = Bridge(
    typing_service=typing_service,
    text_load_service=text_load_service,
    auth_service=auth_service,
    runtime_config=runtime_config,
    char_stats_service=char_stats_service,
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
- 对网络错误、超时、解析异常必须有测试
- 新增文本来源时，需同时补充：
  - `TextUseCase` 测试
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
