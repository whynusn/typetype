<div align="center">
  <img src="resources/images/TypeTypeLogo.png" alt="TypeType Logo" width="200" />
  <h1>TypeType</h1>
  <p>中文打字练习 & 跟打器 — 支持 <b>码长 / 击键 / 速度 / 键准</b> 统计，<b>Linux Wayland</b> 原生可用</p>
  <p>Chinese typing practice tool with keystroke statistics (码长/击键/键准), native Linux Wayland support via evdev</p>

  [![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![PySide6](https://img.shields.io/badge/PySide6-QML-41CD52?logo=qt&logoColor=white)](https://www.qt.io/qt-for-python)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
  [![CI](https://img.shields.io/github/actions/workflow/status/whynusn/typetype/ci.yml?branch=main&label=ci)](https://github.com/whynusn/typetype/actions)
  [![Tests](https://img.shields.io/github/actions/workflow/status/whynusn/typetype/multi-platform-tests.yml?branch=main&label=tests)](https://github.com/whynusn/typetype/actions)
  [![Ruff](https://img.shields.io/badge/style-ruff-261230?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
  [![uv](https://img.shields.io/badge/pkg-uv-DE5FE9?logo=python&logoColor=white)](https://github.com/astral-sh/uv)

  [![Linux](https://img.shields.io/badge/Linux-Wayland-449DD1?logo=linux&logoColor=black)](https://github.com/whynusn/typetype)
  [![Linux](https://img.shields.io/badge/Linux-X11-FCC624?logo=linux&logoColor=black)](https://github.com/whynusn/typetype)
  [![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)](https://github.com/whynusn/typetype)
  [![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)](https://github.com/whynusn/typetype)
  [![Nuitka](https://img.shields.io/badge/pack-Nuitka-2B69C3)](https://github.com/Nuitka/Nuitka)

  ---

</div>

<details>
<summary>📊 统计指标</summary>

| 分类 | 指标 |
|:--- |:--- |
| **会话实时** | 速度（字/分）、击键（击/秒）、码长（击/字）、键准（%）、字准（%）、打词率（%）、错字、回改、退格、标顶、用时（秒）、键数 |
| **峰值** | 峰值速度、峰值击键、峰值码长 |
| **慢字分析** | 慢字（单字符耗时 > 1s 列表） |
| **历史累积** | 今日跟打字数、历史总跟打字数、字符级 SQLite 统计 |

计算公式详见 [typing-metrics.md](docs/reference/typing-metrics.md)。
</details>

> **原理：** 通过 Linux evdev 直接读取内核键盘事件，绕过 Wayland text-input-v3 协议对浏览器/应用层按键事件的屏蔽，实现 Wayland 下的物理击键统计。

---

## 功能概览

- 📊 实时 **速度 / 击键 / 码长 / 键准 / 字准 / 打词率** 统计，配合 **错字 / 回改 / 退格 / 标顶** 分析
- 📈 字符级统计（SQLite 持久化）与薄弱字分析  
- 🏆 服务端排行榜与成绩提交（支持分片模式聚合成绩）  
- 📝 三层文本源：本地文件、开源文库（脚本工具）、即时拉取（服务端/第三方 API）  
- 🪟 跨平台支持（详见 [💻 支持平台](#支持平台)）

---

## 💻 支持平台

| 平台 | 支持状态 | 键盘监听方式 |
| :--- | :--- | :--- |
| **Linux Wayland** | ✅ 原生支持 | `evdev` 直接读取内核事件 |
| **Linux X11** | ✅ 支持 | QML Text 变化统计（`onTextChanged` / `Keys.onPressed`） |
| **macOS** | ✅ 支持 | `Quartz CGEventTap` 全局监听（降级：QML Text 变化统计） |
| **Windows** | ✅ 支持 | QML Text 变化统计（`onTextChanged` / `Keys.onPressed`） |

> 💻 **详细权限配置**：见下方 [Linux Wayland 权限](#linux-wayland-权限) 和 [macOS 输入监控权限](#macos-输入监控权限) 章节。

---

## 为什么 Wayland 下大部分打字工具统计不准？

不了解 Wayland/X11 的区别可以先阅读：[Wayland（Wikipedia）](https://zh.wikipedia.org/wiki/Wayland)。

浏览器（Firefox / Chromium）在 Wayland 下使用 text-input-v3 协议与输入法通信。拼音输入时，**每个按键走 IME composition 流程，浏览器的 keydown/keyup 事件不为拼音按键触发**，只在 compositionend 时提交最终中文字符。因此：

- ❌ 网页版跟打器在 Wayland 上无法统计真实击键数和码长
- ✅ TypeType 使用 **evdev 直接读取 `/dev/input/event*`**，在物理键盘层面计数，不依赖任何显示协议

> 原理：evdev 是 Linux 内核的输入设备接口，在 Wayland 合成器处理键盘事件之前就能拿到原始按键数据。

---

## 快速开始

```bash
uv sync
uv run python main.py
```

> **联网功能说明：** 排行榜、载文等联网功能依赖 [typetype-server](https://github.com/whynusn/typetype-server) 服务端，默认配置指向 `127.0.0.1:8080`。服务端目前处于开发阶段，暂不开放公网访问。如需体验在线服务，可联系 `whynusn@qq.com`，或者参考服务端仓库自行本地部署后修改客户端设置中的 `base_url`。仅使用本地打字功能则无需服务端。

### Linux Wayland 权限

全局键盘监听需要读取 `/dev/input/event*`，通常需要将用户加入 `input` 组：

```bash
sudo usermod -aG input $USER
```

重新登录后生效。若没有该权限，部分指标统计会有问题，但不影响基础打字功能。

### macOS 输入监控权限

macOS 下准确统计中文输入法的物理击键需要 Quartz 全局键盘监听。首次运行时，如果系统未授权，程序会降级到 QML 文本变化统计，基础打字仍可用，但码长/击键会按上屏字符估算。

如需准确击键统计，请在系统设置中授予运行 TypeType 的终端或打包应用以下权限后重启程序：

- 隐私与安全性 → 输入监控
- 隐私与安全性 → 辅助功能

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

## 当前技术栈

| 层 | 技术 |
|:--- |:---|
| 桌面 UI | PySide6 + QML + RinUI |
| 后端语言 | Python 3.12+ |
| 架构 | Clean Architecture + Ports & Adapters |
| 本地持久化 | SQLite |
| 网络请求 | httpx |
| 包管理 | uv |
| 击键监听 | evdev（Linux）/ Quartz CGEventTap（macOS） |

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
domain/         # 纯业务逻辑（TypingService 计算码长/击键/键准）
ports/          # 抽象协议（KeyListener、TextProvider 等 Port 定义）
integration/    # Port 实现（GlobalKeyListener 读 evdev、ApiClient 等）
infrastructure/ # 通用基础设施（网络异常模型、加密等）
models/         # Entity / DTO
workers/        # 后台任务（异步加载文本/排行榜/薄弱字等）
config/         # 运行时配置（RuntimeConfig、文本来源配置）
security/       # 加密与安全存储（crypt、secure_storage）
utils/          # 工具类（Logger、text_id）
```

### 击键统计链路

```text
物理按键 → evdev (/dev/input/event*) → GlobalKeyListener (KeyListener Port 实现)
  → keyPressed 信号 → TypingAdapter.handlePressed()
    → TypingService.accumulate_key() → SessionStat.key_stroke_count
      → 码长 = key_stroke_count / char_count
      → 击键 = key_stroke_count / time
      → 键准 = (key_stroke_count - backspace_count - correction_count × 码长) / key_stroke_count
```

---

## 文本来源

TypeType 的文本来源按**路由方式**（Loader）和**排行榜行为**（LeaderboardMode）二维正交划分，详见 [ARCHITECTURE.md](docs/ARCHITECTURE.md#文本源三层模型)。

### 加载方式分类

| 路由 | 加载机制 | 适用来源 |
|:--- |:--- |:--- |
| **本地文件** | `QtLocalTextLoader` 直接读取本地文件 | 内置示例、前/中/后五百、打词必备单字、本地文库、练单器、剪贴板、自定义载文 |
| **服务端 API** | `RemoteTextProvider` 调用 typetype-server REST API | 服务端提供的文本列表（通过 `config.json` 配置 `text_sources` 注册） |
| **开源文库** | `OttTextProvider` + `OttFederationProvider` 读取 OTT Core v1 / OTT Repo v1（`/ott/v1` 或 Static Profile） | 订阅 OTT Repo 源仓库，内置离线默认源，规则/脚本源（沙箱执行） |
| **独立协议** | 各自独立的 Provider + UseCase + Adapter 栈 | 晴发文（第三方 API）、AI 智能推荐（LLM API） |

### 文本来源列表

**本地来源**（离线可用，无需服务端）：
- **剪贴板**（Ctrl+V / 工具栏按钮）— 从系统剪贴板读取文本，支持 QQ 跟打发信格式解析
- **自定义载文** — 手动输入或从文本列表中选择
- **内置示例** `builtin_demo` — 演示用短文
- **前五百 / 中五百 / 后五百**（`fst_500` / `mid_500` / `lst_500`）— 高频汉字集，支持本地 hash 回查服务端 text_id（排行榜可提交）
- **打词必备单字** `essential_single_char` — 单字练习
- **本地文库** — 用户本地文本文件浏览与载文，支持分片模式
- **练单器** — 词组分组练习，支持乱序与进度追踪

**联网来源**（需配置服务端或第三方服务）：
- **typetype-server 文本列表**（`text_sources` 中 `loader=REMOTE_API` 的条目）— 通过客户端设置页配置的 `base_url` 连接自部署的 [typetype-server](https://github.com/whynusn/typetype-server)，获取服务端提供的文本列表及排行榜
- **开源文库**（OTT Repo 订阅）— 首启自动注入 `file://` 内置离线源；可手动订阅远程 OTT Repo（任意第三方仓库，支持磁盘缓存与后台刷新）。旧 `registry.primary_url` 配置自动迁移为订阅
- **晴发文** — 调用 [qingfawen.fcxxz.com](https://qingfawen.fcxxz.com) 第三方 API 获取随机/相邻文本，需注册账号。独立协议栈，不支持排行榜提交
- **AI 智能推荐** — 通过 OpenAI / DeepSeek / Anthropic 等兼容 API 生成针对性练习文本，根据薄弱字自动出题。独立协议栈

### 分片机制

所有本地来源 + typetype-server 文本共享分片/乱序组件（`TextSessionUseCase` + `FileSegmentProvider` / `InMemorySegmentProvider`）。晴发文在服务端分段，不走客户端分片机制。

### 默认配置

首次启动自动生成 `~/.config/typetype/config.json`，默认 `text_sources` 包含：
- `builtin_demo` / `fst_500` / `mid_500` / `lst_500` / `essential_single_char`（五组本地文件）
- 联网来源需在设置页配置 `base_url`（指向 typetype-server）或订阅 `source_repos`（官方默认仓）后生效

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
  --include-data-files=resources/fonts/LXGWWenKai-Regular-subset.ttf=resources/fonts/LXGWWenKai-Regular-subset.ttf \
  --include-data-dir=resources/trainer=resources/trainer \
  --include-data-dir=resources/ziti=resources/ziti
```

Windows 建议追加：

```text
--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*
```

---

## 开发者文档

| 文档 | 面向 | 职责 | 何时读 |
|:--- |:--- |:--- |:---|
| **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** | 开发者 | 架构事实、分层、数据流 | 理解或修改代码 |
| **[AGENTS.md](./AGENTS.md)** | AI 开发者 | 编码约束、已知陷阱、验证要求 | 让 AI 参与开发 |
| **[docs/guides/](./docs/guides/)** | 开发者/AI | 任务步骤 | 执行具体工作流 |
| **[docs/reference/](./docs/reference/)** | 开发者/AI | 配置、API、QML、指标速查 | 查字段、接口、页面 |
| **[docs/tutorials/](./docs/tutorials/)** | 新贡献者 | 端到端入门教程 | 第一次改代码 |
| **[docs/decisions/](./docs/decisions/)** | 维护者 | 已接受的架构决策 | 理解决策背景 |
| **[docs/history/](./docs/history/)** | 参考 | 旧设计、旧计划、修复记录归档 | 追溯历史 |
| **[docs/meta/README.md](./docs/meta/README.md)** | 维护者 | 文档体系规则 | 调整文档结构 |

---

## 相关搜索关键词

> 中文打字练习, 跟打器, 码长统计, 击键统计, 打字速度测试, Wayland 打字工具, evdev 键盘监听, Linux 中文输入练习, Chinese typing practice, typing tutor, keystroke statistics, code length, typing speed test

---

## 💬 快捷操作（对 AI 说）

在对话中输入「项目概览」「同步文档」「检查文档」「记录决策」「更新 CHANGELOG」等关键词，AI 会自动执行对应操作。完整指令表见 [AGENTS.md](./AGENTS.md) 的「用户快捷操作指令」。

---

## 致谢

- [RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) — Fluent Design 风格 QML 组件库（MIT License © 2025 RinLit）
- [晴发文](https://qingfawen.fcxxz.com) — 中文随机器文 API 服务，为本项目提供随机/相邻文本来源
- [TypeSunny（a810439322）](https://github.com/a810439322) — macOS 适配贡献者（Quartz CGEventTap 键盘监听），同时维护 [TypeSunny（晴跟打）](https://github.com/a810439322/TypeSunny) 开源跟打器项目

---

## 内容与安全声明

- **工具中立性**：TypeType 是打字练习工具，对用户订阅的开源文库、规则（L1）、脚本（L3）及其内容不承担审核或背书责任。启用联网来源前请自行确认来源可信。
- **无广告、无聚合搜索**：TypeType 不含任何广告，也不提供跨来源的聚合搜索/爬取服务。第三方来源的能力边界以来源自身声明为准。
- **脚本风险提示**：开源文库分发的 `ott-script` 脚本在受限沙箱中执行（AST 白名单检查 + 子进程资源限制，Linux 5.13+ 另加 Landlock 文件系统隔离）。沙箱无绝对安全，Windows 平台默认禁用脚本执行，可在设置页手动开启。

---

<div align="center">

## 许可证

MIT © 2026 [whynusn](https://github.com/whynusn)

</div>
