# CLAUDE.md

## 📍 文档导航卡（你在这里）

本文档给 Claude Code 提供项目指导。详细架构见核心文档。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — Claude Code 项目指导 | [README.md](./README.md) — 快速入门<br>[ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 架构权威<br>[AGENTS.md](./AGENTS.md) — 开发规范 | [项目概述](#项目概述)<br>[常用命令](#常用命令)<br>[代码协作要点](#代码协作要点) |

---

## 项目概述

Typetype 是一个 PySide6/QML 打字练习应用，使用 RinUI 作为 QML UI 框架。当前代码已完成一轮分层重构：

- 依赖注入入口：`main.py`
- 用例层：`src/backend/application/usecases`
- 端口协议：`src/backend/ports`（独立层，与 application/domain 平级）
- 集成实现：`src/backend/integration`
- 异步任务：`src/backend/workers`
- QML 桥接：`src/backend/presentation/bridge.py` (`appBridge`)
- UI 框架：`RinUI/`（vendored，不修改）

## 常用命令

```bash
uv sync
uv run python main.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 当前文本加载链路

1. QML `ToolLine` 触发 `requestLoadText(sourceId)`
2. `Bridge.requestLoadText()` 转发到 `TextAdapter.requestLoadText()`
3. 网络来源走 `TextLoadWorker -> LoadTextUseCase.load(source_id)`
4. 本地来源走 `LoadTextUseCase.load(source_id)`
5. 结果通过 `textLoaded` / `textLoadFailed` 信号回传 QML

## 代码协作要点

- 优先保持 `ports -> usecases -> integration` 方向依赖
- 不要在用例层直接依赖 Qt 具体实现
- 新网络能力优先通过 `TextFetcher` 协议接入
- UI 阻塞操作应放入 worker，不直接在 QML 主线程执行
- 新增 adapter 时改 `config/container.py` 的 `create_adapters()` + Bridge 构造参数

## RinUI 集成约定

- `RinUI/` 为本地 vendored 的第三方 QML 框架，**不修改其源码**。
- `pyproject.toml` 中 `[tool.ruff] exclude = ["RinUI"]` 排除 lint。
- UI 字体由 `main.py` 中 `QFontDatabase.addApplicationFont()` + `app.setFont()` 全局设置，QML 层不传递 `fontFamily` 属性。
- RinUI 组件内部通过 `Utils.fontFamily` 读取字体，Linux 上等同于 `Qt.application.font.family`。
- 主题颜色统一使用 `Theme.currentTheme.colors.*`（如 `.textColor`、`.cardColor`、`.backgroundColor`）。
- 若 QML 中需要同时使用 RinUI 和 Qt 同名组件（如 `TextArea`、`ScrollBar`），使用 `import RinUI as Rin` 避免冲突。
- Nuitka 打包时需通过 `--include-package=RinUI` + `--include-data-dir` 显式包含 RinUI 的 Python 模块和 QML/资源文件。

## Spring Boot 后端（已接入）

后端已在 typetype-server 项目中实现。当前使用的接口：

- `GET /api/v1/texts/latest/{sourceKey}` — 获取指定来源的最新文本
- `GET /api/v1/texts/catalog` — 获取所有可用文本来源
- `POST /api/v1/scores` — 提交成绩（只发 textId，不发 sourceKey/content）
- `GET /api/v1/texts/{textId}/leaderboard` — 获取文本排行榜

### 成绩提交规则

只有服务端存在的文本才能提交成绩。成绩提交只传 textId（服务端主键），服务端直接 findById。
本地文件和剪贴板仅用于练习，不提交成绩。文本入库通过管理员 API 或服务端自动抓取。

### 错误与超时

继续沿用 `src/backend/infrastructure/network_errors.py`：

- `NetworkTimeoutError`
- `NetworkRequestError`
- `NetworkHttpStatusError`
- `NetworkDecodeError`

## CI 约束

- `ci.yml`: ruff check + format check
- `multi-platform-tests.yml`: Linux/Windows pytest
- `build-release.yml`: Nuitka 打包并发布

提交前至少保证本地执行通过：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
