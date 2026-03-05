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
uv run pyside6-rcc resources.qrc -o rc_resources.py
uv run python -m nuitka main.py \
  --follow-imports \
  --enable-plugin=pyside6 \
  --include-qt-plugins=qml \
  --output-dir=deployment \
  --quiet \
  --noinclude-qt-translations \
  --standalone \
  --include-data-dir=src=./src \
  --include-data-dir=resources=./resources
```

## 2. 当前架构（以代码为准）

```text
src/backend/
├── application/
│   ├── ports/       # 协议：Clipboard/TextFetcher/LocalTextLoader
│   └── usecases/    # 业务编排：TextUseCase/ScoreUseCase
├── core/            # ApiClient 与网络异常模型
├── integration/     # Qt/系统层实现（本地文本加载、键盘监听等）
├── services/        # 具体网络服务（如 SaiWenService）
├── workers/         # 后台任务（避免阻塞 UI）
└── text_properties.py  # Bridge（appBridge）
```

关键点：

- 依赖注入在 `main.py` 完成，不再使用全局 registry。
- QML 通过 `appBridge` 与后端交互。
- 文本加载支持 `network` 与 `local` 两类来源。

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
