# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Typetype 是一个基于 PySide6 的跨平台打字测试工具，提供实时打字速度统计（WPM）、键盘监听和网络获取打字内容功能。主要支持 Linux 和 Windows 平台，使用 Qt/QML 构建响应式用户界面。

## 常用命令

### 开发环境设置
```bash
# 安装依赖
uv sync

# 运行应用
uv run python main.py
```

### 测试
```bash
# 运行所有测试
uv run pytest

# 运行特定文件
uv run pytest path/to/file.py

# 运行单个函数
uv run pytest -k test_name

# 详细输出
uv run pytest -v
```

### 代码检查
```bash
uv run ruff check .
uv run ruff format --check .
```

### 打包
```bash
# 安装/升级打包工具
uv run python -m ensurepip --upgrade
uv pip install --upgrade nuitka --index-url https://pypi.org/simple

# 编译资源
uv run pyside6-rcc resources.qrc -o rc_resources.py

# 执行打包（Nuitka）
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
Windows 平台建议增加参数：`--assume-yes-for-downloads`。

## 架构概述

### 核心组件

**后端（src/backend/）**
- `backend.py`: QML 上下文后端入口，负责平台标记和按键转发
- `text_properties.py`: 计算打字指标（WPM、准确率等），处理文本比较逻辑
- `core/api_client.py`: 通用 HTTP 客户端
- `services/sai_wen_service.py`: 赛文文本请求服务（业务逻辑）
- `models/score_dto.py`: 传输对象（DTO）
- `typing/score_data.py`: 成绩领域模型与统计计算
- `integration/global_key_listener.py`: Linux 全局键盘监听器，使用 evdev 处理设备事件
- `integration/system_identifier.py`: 检测操作系统和显示服务器
- `security/crypt.py`: 加密工具，处理第三方接口协议

**前端（src/qml/）**
- `Main.qml`: 应用主界面容器
- `UpperPane.qml`: 显示练习文本和统计信息
- `LowerPane.qml`: 用户输入区域和工具栏
- `AppText.qml`: 文本显示组件
- `EndDialog.qml`: 打字结束后的统计对话框
- `HistoryArea.qml`: 历史记录展示
- `ScoreArea.qml`: 实时分数统计
- `ToolLine.qml`: 工具栏组件

### 关键设计模式

**Qt 集成模式**
- 后端类继承 `QObject`，使用 `@Property` 装饰器暴露属性给 QML
- 使用信号槽机制进行 Python-QML 通信（如 `typeSpeedChanged` 信号）
- 后端通过 `setContextProperty` 暴露为 QML 单例，访问路径为 `src.backend`

**平台适配**
- 运行时检测操作系统和显示服务器（X11/Wayland）
- Linux 系统使用全局键盘监听器，其他平台降级处理
- 平台特定功能优雅降级，避免应用崩溃

**实时统计**
- 使用 QTimer（100ms 间隔）计算实时打字速度
- 键盘事件流经监听器 -> 后端 -> QML 的单向数据流
- 支持暂停/继续功能，状态持久化

### 数据流

```
键盘输入 → GlobalKeyListener → Backend (事件处理)
                          ↓
Backend (计算指标) → 信号 → QML (UI更新)
                          ↓
网络请求 → SaiWenService → Backend (文本更新)
                          ↓
加密处理 → security/crypt → Backend (数据安全)
```

## 文档维护

### README 更新
- 当添加新功能时，务必更新 README.md 中的功能特性列表
- Wayland 权限说明已在文档中，开发时注意测试相关功能
- 请手动保持文档与代码同步

## 开发注意事项

### 代码风格
- 类型提示强制使用：所有函数参数和返回值必须标注
- 命名规范：类名 PascalCase，函数变量 snake_case，私有方法 `_` 前缀
- 导入顺序：标准库 → 第三方包 → 本地导入，同包使用相对导入
- 错误处理：对外部 API 调用使用 try-except，用 print 记录错误

### Qt/QML 特殊要求
- 信号命名以 `Changed` 结尾（如 `typeSpeedChanged`）
- 定时器作为实例变量存储，正确管理生命周期
- QML 文件使用 `src.backend` 路径访问 Python 模块

### 平台兼容性和权限
- **Wayland 环境**：需要将用户加入 input 组或使用 sudo 运行，否则键盘监听功能不可用
- **X11 环境**：通常无需额外配置
- **Windows 平台**：需要降级处理，避免使用 Linux 特有 API（如 evdev）
- 测试时注意在 Linux 系统上验证权限设置

### 依赖管理
- 所有依赖在 `pyproject.toml` 的 `[project.dependencies]` 中声明
- 使用 `uv sync` 管理，锁定文件 `uv.lock` 确保可重现构建
- PySide6 项目配置在 `[tool.pyside6-project]` 中指定需要包含的文件
- **evdev 依赖**：在 Linux 系统上需要系统级权限，建议将用户加入 input 组
