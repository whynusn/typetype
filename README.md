# TypeType

TypeType 是一个基于 **PySide6 + QML** 的跨平台中文打字练习工具。

它当前提供：

- 本地文本与网络文本统一载文
- 实时速度 / 击键 / 码长 / 错误数统计
- 打字结束成绩弹窗与历史记录展示
- 字符级统计（SQLite 持久化）与薄弱字页面
- Linux Wayland 下的全局键盘监听降级支持

---

## 当前技术栈

- **桌面 UI**：PySide6 + QML + RinUI
- **后端语言**：Python 3.12+
- **架构**：Clean Architecture + Ports & Adapters
- **本地持久化**：SQLite
- **网络请求**：httpx
- **包管理**：uv

---

## 快速开始

```bash
uv sync
uv run python main.py
```

---

## 常用命令

```bash
# 运行
uv run python main.py

# 测试
uv run pytest

# 代码检查
uv run ruff check .
uv run ruff format --check .

# 自动格式化
uv run ruff format .
```

---

## 当前项目结构（核心）

```text
typetype/
├── main.py
├── docs/
├── config/
├── resources/
├── src/
│   ├── backend/
│   └── qml/
├── tests/
└── RinUI/
```

### `src/backend/` 分层

```text
presentation/   # Bridge + Adapters，负责 QML/Qt 适配
application/    # UseCases + Gateways，负责编排与边界整合
domain/         # 纯业务逻辑
ports/          # 抽象协议
integration/    # Port 实现
infrastructure/ # ApiClient / 网络异常等通用基础设施
models/         # Entity / DTO
workers/        # 后台任务
```

### QML 主入口

- `src/qml/Main.qml`
- 打字主页面：`src/qml/pages/TypingPage.qml`

---

## 核心架构一句话

QML 不直接碰业务，Domain 不直接碰 Qt。

当前主链路示例：

```text
QML
  -> Bridge
  -> Adapter
  -> UseCase / Domain Service
  -> Port / Integration
  -> 结果通过 Signal 回到 QML
```

文本加载当前实际链路：

```text
Bridge -> TextAdapter -> LoadTextUseCase -> TextSourceGateway
```

更完整的架构说明见 [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)。

---

## 文本来源

当前默认配置中包含：

- 网络来源：`jisubei`
- 本地来源：`builtin_demo`、`fst_500`、`mid_500`、`lst_500`、`essential_single_char`

配置文件示例见：`config/config.example.json`

---

## 日志开关

默认只输出 warning 及以上日志，可通过环境变量调整：

- `TYPETYPE_DEBUG=1`
- `TYPETYPE_LOG_LEVEL=debug|info|warning|error|none`

示例：

```bash
TYPETYPE_DEBUG=1 uv run python main.py
```

---

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
  --noinclude-dlls=libQt6WebEngine* \
  --include-data-dir=src/qml=src/qml \
  --include-data-dir=resources/texts=resources/texts \
  --include-data-files=resources/images/TypeTypeLogo.png=resources/images/TypeTypeLogo.png \
  --include-data-files=resources/fonts/HarmonyOS_Sans_SC_Regular-subset.ttf=resources/fonts/HarmonyOS_Sans_SC_Regular-subset.ttf \
  --include-data-files=resources/fonts/LXGWWenKai-Regular-subset.ttf=resources/fonts/LXGWWenKai-Regular-subset.ttf
```

Windows 建议追加：

```text
--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*
```

---

## Linux Wayland 权限说明

若需要全局键盘监听，通常需要：

```bash
sudo usermod -aG input $USER
```

重新登录后生效。即使没有该权限，程序也会尽量优雅降级，不影响基础打字功能。

---

## 开发者文档

开发建议从这里开始：

- [docs/README.md](./docs/README.md) —— 文档索引
- [docs/DEVELOPING.md](./docs/DEVELOPING.md) —— 上手与开发流程
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) —— 当前事实架构
- [docs/roadmap.md](./docs/roadmap.md) —— 功能路线图与后续方向
- [AGENTS.md](./AGENTS.md) —— 仓库级开发约束与已知陷阱

---

## 许可证

MIT
