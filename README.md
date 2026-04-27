<div align="center">
  <img src="resources/images/TypeTypeLogo.png" alt="TypeType Logo" width="200" />
  <h1>TypeType</h1>
  <p>中文打字练习 & 跟打器 — 支持 <b>码长 / 击键 / 速度 / 键准</b> 专业统计，<b>Linux Wayland</b> 原生可用</p>
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

TypeType 是一个基于 **PySide6 + QML** 的中文打字练习跟打器，提供打字圈常用的专业统计指标：

- **码长**（击/字）— 每个中文字符平均消耗的按键次数
- **击键**（击/秒）— 每秒物理按键次数
- **速度**（字/分钟）— 每分钟输入中文字符数
- **键准**（%）— 有效按键比例，反映按键效率（错键率）
- **错字 / 回改 / 退格** — 错误修正统计

> **核心优势：** 通过 Linux evdev 直接读取内核键盘事件，**完全绕过 Wayland text-input-v3 协议对浏览器/应用层按键事件的屏蔽**，实现 Wayland 下真实的物理击键统计。这是目前少数能在 Wayland 上准确统计码长和击键的打字工具之一。

---

## 功能概览

- 📊 实时 **码长 / 击键 / 速度 / 键准** 统计，配合 **错字 / 回改 / 退格** 分析
- 📈 字符级统计（SQLite 持久化）与薄弱字分析
- 🏆 服务端排行榜与成绩提交（支持分片模式聚合成绩）
- 📝 本地文本与网络文本统一载文
- 🐧 Linux Wayland 原生支持（evdev 全局键盘监听）
- 🍎 macOS 原生键盘监听（Quartz CGEventTap，需系统权限）
- 🪟 跨平台：Linux (Wayland / X11) + macOS + Windows

---

## 为什么 Wayland 下大部分打字工具统计不准？

不了解 Wayland/X11 的区别可以先阅读：[《细说 Wayland 和 X11》](https://blog.csdn.net/yang1fei2/article/details/139576188)。

浏览器（Firefox / Chromium）在 Wayland 下使用 text-input-v3 协议与输入法通信。拼音输入时，**每个按键走 IME composition 流程，浏览器的 keydown/keyup 事件不为拼音按键触发**，只在 compositionend 时提交最终中文字符。因此：

- ❌ 网页版跟打器（jsxiaoshi.com、91小键人等）在 Wayland 上无法统计真实击键数和码长
- ✅ TypeType 使用 **evdev 直接读取 `/dev/input/event*`**，在物理键盘层面计数，不依赖任何显示协议

> 原理：evdev 是 Linux 内核的输入设备接口，在 Wayland 合成器处理键盘事件之前就能拿到原始按键数据。

---

## 快速开始

```bash
uv sync
uv run python main.py
```

> **联网功能说明：** 排行榜、载文等联网功能依赖 [typetype-server](https://github.com/whynusn/typetype-server) 服务端，默认配置指向 `127.0.0.1:8080`。当前服务端还存在不少安全性问题，所以 IP 暂不便公开。想体验在线服务可以联系 `whynusn@qq.com`，或者参考服务端仓库自行本地部署后修改 `config/config.example.json` 中的 `base_url`。仅使用本地打字功能则无需服务端。

### Linux Wayland 权限

全局键盘监听需要读取 `/dev/input/event*`，通常需要将用户加入 `input` 组：

```bash
sudo usermod -aG input $USER
```

重新登录后生效。即使没有该权限，程序也会优雅降级，不影响基础打字功能。

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
|------|------|
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
```

### 击键统计链路

```text
物理按键 → evdev (/dev/input/event*) → GlobalKeyListener (KeyListener Port 实现)
  → keyPressed 信号 → TypingAdapter.handlePressed()
    → TypingService.accumulate_key() → SessionStat.key_stroke_count
      → 码长 = key_stroke_count / char_count
      → 击键 = key_stroke_count / time
      → 键准 = (key_stroke_count - backspace - correction × 码长) / key_stroke_count
```

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

Windows 建议追加：

```text
--assume-yes-for-downloads --windows-console-mode=disable --include-windows-runtime-dlls=yes --noinclude-dlls=Qt6WebEngine*
```

---

## 开发者文档

从 [ARCHITECTURE.md](./docs/ARCHITECTURE.md) 开始 — 快速开始、架构、数据流、陷阱全在里面。

- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 唯一事实来源（"宪法"）
- [docs/reference/](./docs/reference/) — 配置/QML/API 速查表
- [docs/history/](./docs/history/) — 历史设计文档归档
- [AGENTS.md](./AGENTS.md) — AI Agent 开发约束

---

## 相关搜索关键词

> 中文打字练习, 跟打器, 码长统计, 击键统计, 打字速度测试, Wayland 打字工具, evdev 键盘监听, Linux 中文输入练习, Chinese typing practice, typing tutor, keystroke statistics, code length, typing speed test

---

## 致谢

- [RinUI](https://github.com/RinLit-233-shiroko/Rin-UI) — Fluent Design 风格 QML 组件库（MIT License © 2025 RinLit）

---

<div align="center">

## 许可证

MIT © 2026 [whynusn](https://github.com/whynusn)

</div>
