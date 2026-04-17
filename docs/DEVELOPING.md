# TypeType 开发指南

> 最后更新：2026-04-17
>
> 目标：让第一次接手 TypeType 的开发者，能在最短时间内把项目跑起来、看懂主链路，并知道新需求该落在哪一层。

---

## 快速开始

### 环境要求

- Python 3.12+
- `uv` 0.9.26+
- Linux / Windows（macOS 理论可运行，但未完整验证）

### 安装与启动

```bash
uv sync
uv run python main.py
```

### 提交前最低检查

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

---

## 第一次接手时，先读这 6 个文件

按这个顺序看，理解速度最快：

1. `main.py` —— 所有对象在哪里创建、怎么注入
2. `src/backend/presentation/bridge.py` —— QML 与 Python 的总入口
3. `src/backend/presentation/adapters/text_adapter.py` —— 文本加载的 Qt 适配层
4. `src/backend/application/usecases/load_text_usecase.py` —— 文本加载编排入口
5. `src/backend/application/gateways/text_source_gateway.py` —— 来源路由与 Port 适配
6. `src/backend/domain/services/typing_service.py` —— 核心打字统计逻辑与高风险坑位

看完这 6 个文件，基本就能解释项目主干原理。

---

## 项目现在到底是什么结构

### 顶层目录速查

```text
typetype/
├── main.py                 # 启动入口 + 依赖注入
├── docs/                   # 开发文档
├── config/                 # JSON 配置文件
├── src/qml/                # QML 页面与组件
├── src/backend/            # Python 后端分层代码
├── resources/              # 字体、图片、内置文本
├── tests/                  # 单元测试
├── RinUI/                  # vendored 第三方 UI 框架（不修改）
└── .github/workflows/      # CI / 测试 / 打包流程
```

### `src/backend/` 分层速查

```text
presentation/   # Bridge + Adapters，处理 QML/Qt 细节
application/    # UseCases + Gateways，处理编排、边界整合
domain/         # 纯业务逻辑，不依赖 Qt
ports/          # 协议定义（抽象依赖）
integration/    # Port 实现（Qt/SQLite/HTTP/系统能力）
infrastructure/ # 通用基础设施（ApiClient、网络异常）
models/         # Entity / DTO
workers/        # 后台任务（QRunnable）
```

更完整的职责与边界说明见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 程序启动时发生了什么

`main.py` 做了这些事：

1. 创建 `QGuiApplication`
2. 注册全局 UI 字体（HarmonyOS）
3. 读取 `RuntimeConfig`
4. 创建基础设施对象：`ApiClient`、`QtLocalTextLoader`、`QtAsyncExecutor`
5. 创建集成实现：`RemoteTextProvider`、`SqliteCharStatsRepository`、`ApiClientAuthProvider`、`LeaderboardFetcher`
6. 创建领域服务：`TypingService`、`CharStatsService`、`AuthService`
7. 创建应用层对象：`ScoreGateway`、`TextSourceGateway`、`LeaderboardGateway`、`LoadTextUseCase`
8. 创建适配层对象：`TypingAdapter`、`TextAdapter`、`AuthAdapter`、`CharStatsAdapter`、`LeaderboardAdapter`、`UploadTextAdapter`
9. 创建 `Bridge`，注入为 QML 全局 `appBridge`
10. 加载 `src/qml/Main.qml`

这意味着：**依赖注入统一发生在 `main.py`，没有全局 registry。**

---

## QML 是怎么和 Python 通信的

### 主入口

- QML 全局对象：`appBridge`
- Python 门面：`src/backend/presentation/bridge.py`

### 常见调用方向

```text
QML 事件
  -> Bridge Slot
  -> Adapter
  -> UseCase / Domain Service
  -> 结果通过 Signal 回到 QML
```

### 一个真实例子：载文

```text
TypingPage.qml / ToolLine.qml
  -> appBridge.requestLoadText(sourceKey)
  -> TextAdapter.requestLoadText(sourceKey)
  -> LoadTextUseCase.plan_load(sourceKey)
  -> LoadTextUseCase.load(plan)
  -> TextSourceGateway.load_from_plan(sourceEntry)
  -> LocalTextLoader 或 RemoteTextProvider
  -> TextAdapter 发射 textLoaded / textLoadFailed
  -> QML 更新文本框
```

---

## 新需求来了，先怎么判断改哪里

### 1. 先问：这是 UI 适配，还是业务规则？

| 场景 | 应该改哪里 |
|------|------------|
| 新增 QML 属性、信号、Slot | `Bridge` / `Adapter` |
| 新增线程协调、Qt 状态管理 | `Adapter` / `workers/` |
| 新增业务流程编排 | `application/usecases/` |
| 新增来源路由、DTO/边界适配 | `application/gateways/` |
| 新增纯业务规则 | `domain/services/` |
| 新增外部依赖实现 | `ports/` + `integration/` |
| 新增持久化实现 | `ports/` + `integration/` + `domain/service` |

### 2. 再问：到底需不需要 UseCase？

**需要 UseCase：**
- 有跨组件编排
- 有流程分支判断
- 需要统一封装入口

**不需要 UseCase：**
- 只是 Adapter 调一个纯业务 Service
- 没有编排，只是简单转发

当前代码里的典型对比：
- `TextAdapter -> LoadTextUseCase`：**需要**，因为有文本加载编排
- `TypingAdapter -> TypingService`：**不需要 UseCase**，因为这是纯业务逻辑直连

---

## RuntimeConfig 与配置文件

### 当前配置入口

`RuntimeConfig.load_from_file()` 会按顺序查找：

1. `~/.config/typetype/config.json`
2. 项目内 `config/config.json`
3. 项目内 `config/config.example.json`

### 你最常改的配置项

- `base_url`
- `api_timeout`
- `default_text_source_key`
- `text_sources`

示例见：`config/config.example.json`

### 文本来源怎么判断同步/异步

当前规则很简单：
- 有 `local_path` → 本地文件 → `sync`
- 没有 `local_path` → 远程来源 → `async`

这个判断在 `TextLoadPlan.execution_mode`（由 `TextSourceGateway.plan_load()` 得到来源后计算），不是在 QML，也不是在 `TextAdapter` 里拍脑袋决定。

---

## 常用开发命令

### 运行

```bash
uv run python main.py
```

### 测试

```bash
uv run pytest
uv run pytest tests/test_text_usecase.py
uv run pytest -v
```

### 代码质量

```bash
uv run ruff check .
uv run ruff format --check .
uv run ruff format .
```

### 调试日志

```bash
TYPETYPE_DEBUG=1 uv run python main.py
TYPETYPE_LOG_LEVEL=info uv run python main.py
```

可选日志级别：`debug / info / warning / error / none`

## 日志系统使用规范

### 基本使用

项目使用 Python 标准库 `logging` 模块，提供统一的日志输出。推荐方式：

```python
from src.backend.utils.logger import log_debug, log_info, log_warning, log_error

log_debug("调试信息")
log_info("普通信息")
log_warning("警告信息")
log_error("错误信息")
```

或者直接使用标准 `logging` API：

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("调试信息")
logger.info("普通信息")
```

### 日志级别约定

| 级别 | 使用场景 |
|------|----------|
| DEBUG | 开发调试信息，用户通常不需要看到 |
| INFO | 正常运行的关键节点信息（如启动、平台检测结果） |
| WARNING | 不影响运行的异常情况 |
| ERROR | 错误信息，功能出错但程序可以继续运行 |

### 输出位置

- **控制台**: 带 ANSI 颜色高亮输出，按级别区分颜色
- **日志文件**: `~/.typetype/app.log`，自动轮转（10MB/文件，保留 5 个备份）

### 开发规范

- **禁止** 在正式代码中使用裸 `print()`，统一使用日志 API
- **RinUI/** 第三方库例外，按约定不修改其源码
- 错误信息使用 `log_error()`，不要用 `print()` 直接打栈跟踪

---

## 当前页面结构（QML）

入口在 `src/qml/Main.qml`，当前导航页包括：

- `pages/TypingPage.qml`
- `pages/WeakCharsPage.qml`
- `pages/DailyLeaderboard.qml`
- `pages/WeeklyLeaderboard.qml`
- `pages/AllTimeLeaderboard.qml`
- `pages/TextLeaderboardPage.qml`
- `pages/UploadTextPage.qml`
- `pages/ProfilePage.qml`
- `pages/SettingsPage.qml`

其中打字主页面又拆成：

- `typing/ToolLine.qml`
- `typing/UpperPane.qml`
- `typing/ScoreArea.qml`
- `typing/LowerPane.qml`
- `typing/HistoryArea.qml`
- `typing/EndDialog.qml`
- `typing/LeaderboardPanel.qml`

---

## 当前测试与 CI 是怎么组织的

### 本地测试文件

当前仓库有 18 个 `tests/test_*.py` 文件，覆盖重点在：

- `ApiClient`
- `TextSourceGateway`
- `LoadTextUseCase`
- `TextAdapter`
- `CharStatsRepository`
- `SessionStat`
- 安全与系统适配能力

### GitHub Actions

- `ci.yml` —— `ruff check` + `ruff format --check`
- `multi-platform-tests.yml` —— Linux / Windows 跑 pytest
- `build-release.yml` —— Nuitka 打包发布

---

## 提交与协作约定

### Commit message

仓库当前使用 **Conventional Commits** 风格，提交信息格式为：

```text
<type>: <简要描述>

<可选 body：背景、方案取舍、注意事项>
```

常用 type：`feat`（新功能）、`fix`（修复）、`refactor`（重构）、`docs`（文档）、`test`（测试）、`style`（格式）、`merge`（合并）。

如果你只是本地试验、不会提交，可以暂时忽略；但正式提交请遵守仓库约定。

### 开发者最常见工作流

1. 先看 `main.py` 找注入关系
2. 定位需求属于哪一层
3. 先补/改测试，再改实现
4. 跑：`pytest + ruff check + ruff format --check`
5. 若改动涉及边界或分层，更新 `docs/ARCHITECTURE.md`
6. 若改动影响上手流程，更新 `docs/DEVELOPING.md`

---

## 高风险坑位

### 1. `TypingService.clear()` 不能清零 `char_count` / `wrong_char_count`

原因：QML 的 `onTextChanged` 是异步的；如果在 `clear()` 中提前清零，未处理完的事件会用 `char_count=0` 算出负数位置，触发：

```text
QTextCursor::setPosition: Position 'X' out of range
```

正确做法：在 `set_total_chars()` 中清零。

### 2. `handle_committed_text()` 删除字符时，顺序不能改

正确顺序是：

1. 先处理 `s`
2. 再清除被删除位置
3. 最后更新 `char_count`

如果先更新 `char_count`，索引就会错。

### 3. “QML 不指定字体”不是绝对规则

- **UI 默认字体** 由 `main.py -> app.setFont()` 统一设置
- **阅读/跟打正文区** 会在 `TypingPage.qml` 中显式使用 `LXGWWenKai-Regular-subset.ttf`

所以更准确的说法是：**普通 UI 不要各处乱配字体；正文阅读区的专用字体属于例外且已集中管理。**

---

## 平台注意事项

### Linux Wayland 全局键盘监听

如果需要 Wayland 下的全局键盘监听，通常需要：

```bash
sudo usermod -aG input $USER
```

重新登录后生效。若权限不足，应用会降级，不影响基础打字流程。

---

## 打包发布（Nuitka）

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

Windows 额外参数：

```text
--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*
```

---

## 相关文档

- [README.md](./README.md) —— 开发文档索引
- [ARCHITECTURE.md](./ARCHITECTURE.md) —— 当前事实架构
- [roadmap.md](./roadmap.md) —— 功能路线图（规划）
- [SPRING_BOOT.md](./SPRING_BOOT.md) —— 后端设计方案（规划）
- [AI_AGENT_PLAN.md](./AI_AGENT_PLAN.md) —— AI Agent 改造方案（规划）
- [../AGENTS.md](../AGENTS.md) —— 仓库级硬约束与陷阱补充

---

## 版本历史

|| 日期 | 变更 |
||------|------|
|| 2026-04-17 | 补充 LeaderboardAdapter/Gateway/Worker、UploadTextAdapter 到启动步骤和 QML 组件列表 |
|| 2026-04-06 | 基于当前代码重写上手路径、修正 CI/链接/提交规范、补充真实开发流程与坑位 |
