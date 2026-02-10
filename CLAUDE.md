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
# 运行所有测试（项目中暂无测试文件）
uv run pytest

# 运行特定文件
uv run pytest path/to/file.py

# 运行单个函数
uv run pytest -k test_name

# 详细输出
uv run pytest -v
```

### 打包
```bash
# 安装打包工具
uv pip install pip nuitka

# 执行打包
pyside6-deploy -c pysidedeploy.spec --extra-ignore-dirs .venv
```

## 架构概述

### 核心组件

**后端（src/backend/）**
- `backend.py`: 主要后端逻辑，连接 QML 和键盘监听，继承 QObject 实现 Qt 集成
- `text_properties.py`: 计算打字指标（WPM、准确率等），处理文本比较逻辑
- `get_sai_wen.py`: 使用 httpx 发送网络请求获取打字练习内容
- `crypt.py`: 加密工具，处理敏感数据
- `global_key_listener.py`: Linux 全局键盘监听器，使用 evdev 处理设备事件
- `system_identifier.py`: 检测操作系统和显示服务器类型

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
网络请求 → GetSaiWen → Backend (文本更新)
                          ↓
加密处理 → Crypt → Backend (数据安全)
```

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

### 平台兼容性
- 测试时注意 Linux 特定功能（如 evdev 需要 root 权限）
- Wayland 和 X11 的键盘监听行为可能不同
- Windows 平台需要降级处理，避免使用 Linux 特有 API

### 依赖管理
- 所有依赖在 `pyproject.toml` 的 `[project.dependencies]` 中声明
- 使用 `uv sync` 管理，锁定文件 `uv.lock` 确保可重现构建
- PySide6 项目配置在 `[tool.pyside6-project]` 中指定需要包含的文件