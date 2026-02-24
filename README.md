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

当前 CI 使用 **Nuitka + PySide6 插件** 打包（不再使用 `pyside6-deploy`）。

### 本地打包步骤（与 CI 一致）

1. 准备干净构建目录：

```bash
mkdir -p build-src
cp -a main.py pyproject.toml uv.lock resources.qrc src resources build-src/
cd build-src
uv sync --frozen
```

2. 安装/升级打包工具并编译资源：

```bash
uv run python -m ensurepip --upgrade
uv pip install --upgrade nuitka --index-url https://pypi.org/simple
uv run pyside6-rcc resources.qrc -o rc_resources.py
```

3. 执行 Nuitka 打包：

```bash
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

Windows 下建议追加参数：`--assume-yes-for-downloads`（允许自动下载 dependency walker）。

打包完成后，产物位于 `deployment/`（部分工具链场景可能输出到 `dist/`）。

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
│   │   ├── backend.py         # QML 上下文后端入口
│   │   ├── text_properties.py # 打字过程属性桥接
│   │   ├── core/
│   │   │   └── api_client.py  # 通用 HTTP 客户端
│   │   ├── services/
│   │   │   └── sai_wen_service.py # 赛文接口服务
│   │   ├── models/
│   │   │   └── score_dto.py   # 传输对象（DTO）
│   │   ├── typing/
│   │   │   └── score_data.py  # 打字成绩领域模型
│   │   ├── integration/
│   │   │   ├── global_key_listener.py # Linux 键盘监听器
│   │   │   └── system_identifier.py   # 操作系统检测
│   │   └── security/
│   │       └── crypt.py       # 加密工具
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
- `elevate>=0.1.3` - Linux 权限提升辅助
- `httpx>=0.28.1` - HTTP 客户端
- `pycryptodome>=3.23.0` - 加密库

## 开发

### 代码风格

- 本地检查命令与 CI 对齐：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest --verbose
```

- 使用 snake_case 命名函数和变量
- 使用 PascalCase 命名类
- 函数必须包含类型提示
- 所有导入放在文件顶部
- 类从 `QObject` 继承以实现 Qt 集成

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
