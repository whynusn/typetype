# Typetype

一个基于 PySide6 的打字测试工具，专注于提供流畅的打字体验和实时性能监控。

## 功能特性

- 实时打字速度统计
- WPM（每分钟单词数）计算
- 键盘按键监听
- 网络请求处理（获取赛文/文章）
- 成绩数据管理
- Linux 全局键盘监听
- 操作系统和显示服务器自动检测
- Qt/QML 响应式 UI
- 打字结束统计对话框

## 系统要求

- Python 3.12 或更高版本
- Linux 或 Windows 操作系统
- Linux 系统：X11 或 Wayland 显示服务器
- Windows 系统：无需额外配置

## 快速开始

如果你只需要快速运行：

```bash
git clone https://github.com/whynusn/typetype.git
cd typetype
uv sync
uv run python main.py
```

## 安装

### 系统要求

- **Python**: 3.12 或更高版本
- **操作系统**: Linux 或 Windows
- **显示服务器**:
  - Linux: X11 或 Wayland
  - Windows: 无需额外配置

### Linux 特殊说明

在 **Wayland** 环境下，使用全局键盘监听功能需要特殊权限：

```bash
# 方法1：使用 sudo 运行（不推荐）
sudo uv run python main.py

# 方法2：将用户加入 input 组（推荐）
sudo usermod -aG input $USER
# 然后重新登录或重启
```

在 **X11** 环境下通常无需额外配置。

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/whynusn/typetype.git
cd typetype
```

### 2. 安装依赖

使用 uv 包管理器：

```bash
uv sync
```

### 3. 运行应用

```bash
uv run python main.py
```

## 打包

### 前置依赖

使用 uv 安装打包所需工具：

```bash
uv pip install pip pyside6
```

### 资源文件编译

项目使用 `.qrc` 文件管理资源（图标、图片等）。在打包前需要编译资源文件：

```bash
# 将 resources.qrc 编译为 Python 模块
pyside6-rcc resources.qrc -o rc_resources.py
```

### 打包配置

项目使用 `pyproject.toml` 中的 `[tool.pyside6-project]` 维护打包文件清单，无需 `pysidedeploy.spec`。
为避免将开发目录（如 `.venv`、`.github`）误打进产物，建议在干净的构建目录中执行打包。

### 打包步骤

1. 安装项目依赖：

```bash
mkdir -p build-src
cp -a main.py pyproject.toml uv.lock resources.qrc src resources build-src/
cd build-src
UV_PROJECT_ENVIRONMENT=/tmp/typetype-venv uv sync --frozen
UV_PROJECT_ENVIRONMENT=/tmp/typetype-venv uv run python -m ensurepip --upgrade
```

2. 编译资源文件（如资源有更新）：

```bash
UV_PROJECT_ENVIRONMENT=/tmp/typetype-venv uv run pyside6-rcc resources.qrc -o rc_resources.py
```

3. 执行打包：

```bash
UV_PROJECT_ENVIRONMENT=/tmp/typetype-venv uv run pyside6-deploy main.py --mode standalone --extra-ignore-dirs .venv,.git,.github,.pytest_cache,.ruff_cache,.claude,tests,typetype.dist,deployment,dist --name typetype -f
```

打包完成后，产物会在 `dist/` 或 `deployment/` 目录（取决于平台和工具版本）。

## 预览

![应用预览](resources/images/swappy-20260203-235018.png)
*应用主界面，显示练习文本和实时统计*

![应用截图](resources/images/swappy-20260203-235205.png)
*打字结束后的统计对话框*

## 项目结构

```
typetype/
├── main.py                    # 应用入口点
├── pyproject.toml             # 项目配置和依赖
├── uv.lock                    # 锁定的依赖
├── src/
│   ├── backend/
│   │   ├── backend.py         # 主要后端逻辑
│   │   ├── crypt.py           # 加密工具
│   │   ├── get_sai_wen.py     # 网络请求处理
│   │   ├── global_key_listener.py  # Linux 键盘监听器
│   │   ├── system_identifier.py   # 操作系统检测
│   │   ├── score_data.py      # 成绩数据管理
│   │   └── text_properties.py    # 文本处理    
│   └── qml/                   # QML UI 文件
│       ├── Main.qml
│       ├── UpperPane.qml
│       ├── LowerPane.qml
│       └── ...
├── README.md                  # 项目文档
└── AGENTS.md                  # 开发指南
```

## 主要依赖

- `PySide6>=6.10.2` - Qt 应用框架
- `qasync>=0.28.0` - Qt 事件循环集成
- `evdev>=1.9.2` - Linux 设备事件处理
- `httpx>=0.28.1` - HTTP 客户端
- `pycryptodome>=3.23.0` - 加密库

## 开发

### 代码风格

- 使用 snake_case 命名函数和变量
- 使用 PascalCase 命名类
- 函数必须包含类型提示
- 所有导入放在文件顶部
- 类从 `QObject` 继承以实现 Qt 集成

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
