# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## 项目概述

Typetype 是一个 PySide6/QML 打字练习应用，使用 RinUI 作为 QML UI 框架。当前代码已完成一轮分层重构：

- 依赖注入入口：`main.py`
- 用例层：`src/backend/application/usecases`
- 端口协议：`src/backend/application/ports`
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
2. `Bridge.requestLoadText()` 根据 `RuntimeConfig` 判断来源类型
3. 网络来源走 `TextLoadWorker -> LoadTextUseCase.load(source_id)`
4. 本地来源走 `LoadTextUseCase.load(source_id)`
5. 结果通过 `textLoaded` / `textLoadFailed` 信号回传 QML

## 代码协作要点

- 优先保持 `ports -> usecases -> integration` 方向依赖
- 不要在用例层直接依赖 Qt 具体实现
- 新网络能力优先通过 `TextFetcher` 协议接入
- UI 阻塞操作应放入 worker，不直接在 QML 主线程执行

## RinUI 集成约定

- `RinUI/` 为本地 vendored 的第三方 QML 框架，**不修改其源码**。
- `pyproject.toml` 中 `[tool.ruff] exclude = ["RinUI"]` 排除 lint。
- UI 字体由 `main.py` 中 `QFontDatabase.addApplicationFont()` + `app.setFont()` 全局设置，QML 层不传递 `fontFamily` 属性。
- RinUI 组件内部通过 `Utils.fontFamily` 读取字体，Linux 上等同于 `Qt.application.font.family`。
- 主题颜色统一使用 `Theme.currentTheme.colors.*`（如 `.textColor`、`.cardColor`、`.backgroundColor`）。
- 若 QML 中需要同时使用 RinUI 和 Qt 同名组件（如 `TextArea`、`ScrollBar`），使用 `import RinUI as Rin` 避免冲突。
- Nuitka 打包时需通过 `--include-package=RinUI` + `--include-data-dir` 显式包含 RinUI 的 Python 模块和 QML/资源文件。

## Spring Boot 接入说明（计划）

当前尚未正式接入。后续推荐按以下方式实施。

### 接口草案

- `GET /api/v1/texts/random?sourceKey=xxx`
- `GET /api/v1/text-sources`
- `POST /api/v1/scores`

### Python 端改造清单

1. 新增 `SpringBootTextService`，实现 `TextFetcher`。
2. 在 `RuntimeConfig.text_sources` 注册 springboot 来源。
3. 在 `main.py` 注入 springboot service（保留旧 service 作为回退）。
4. 为 `LoadTextUseCase`、`ApiClient` 增加对应测试。

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
