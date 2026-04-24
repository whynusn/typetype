# Ubuntu 24 + Wayland 下 v0.3.7 已知问题诊断与修复指南

> 记录时间：2026-04-24
> 涉及版本：v0.3.7（及此前版本）
> 测试环境：Ubuntu 24.04 LTS + Wayland（低配机器）

---

## 问题现象

| 场景 | 行为 | 预期 |
|------|------|------|
| Nuitka 打包的 `main.bin` 在 Ubuntu 24 上直接运行 | 启动即 **核心转储（core dump）** | 正常启动 |
| 改用 `uv run python main.py` 运行源码 | 程序启动成功，内部逻辑正常 | — |
| 在 LowerPane 的 TextArea 中尝试输入中文 | **fcitx5 输入法无法激活**，无候选框 | 应正常调出 fcitx5 候选 |
| 同一 `main.bin` 在 CachyOS 上运行 | 一切正常 | — |

---

## 根因分析

### 问题一：main.bin 核心转储（概率排序）

#### 1A. GPU / RHI 渲染初始化失败（概率最高）

- Qt6 Quick 默认启用 **RHI（Rendering Hardware Interface）**，在 Wayland 下首选 **OpenGL/EGL** 后端。
- 低配机器往往是老旧核显或极简驱动，可能**不支持 Qt6 RHI 所需的 OpenGL ES 3.0 / OpenGL 3.3 Core Profile**。
- Qt6 Quick 在 EGL 初始化失败时，内部回退逻辑可能空指针解引用，触发 SIGSEGV。
- CachyOS 用户硬件和 Mesa 驱动通常较新，因此正常。

#### 1B. Nuitka 遗漏 Wayland 相关 Qt 插件（概率高）

- 当前打包参数 `--include-qt-plugins=qml` **只显式包含 qml 插件**。
- Wayland 平台正常工作还需要以下插件目录中的文件：
  - `wayland-shell-integration/libxdg-shell.so`（现代 compositor 必需）
  - `wayland-graphics-integration-client/libqt-plugin-wayland-egl.so`
  - `platformthemes/libqxdgdesktopportal.so`（桌面主题/文件选择器）
- 如果 Nuitka 遗漏了 `libxdg-shell.so`，Qt Wayland 平台插件初始化时可能访问无效内存。

#### 1C. CPU 指令集不兼容（概率中等）

- GitHub Actions `ubuntu-latest` 使用较新 Xeon CPU，支持 AVX2。
- Nuitka/GCC 编译时可能针对构建机 CPU 生成优化代码。
- 低配 CPU（老旧 Celeron/Pentium）缺少 AVX/AVX2，执行到相关指令触发 SIGILL。
- 但 SIGILL 通常报"非法指令"而非"核心转储"，优先级略低。

### 问题二：fcitx5 输入法无法激活

#### 决定性发现

在项目 `.venv` 中查验 PySide6 自带插件：

```
platforminputcontexts/
├── libcomposeplatforminputcontextplugin.so
├── libibusplatforminputcontextplugin.so
└── libqtvirtualkeyboardplugin.so
```

**没有 `libfcitx5platforminputcontextplugin.so`**。

#### 技术背景

fcitx5 在 Wayland 下与 Qt6 应用交互有两条路径：

| 路径 | 需要的条件 | 本项目现状 |
|------|-----------|-----------|
| **A. fcitx5 IM Module**（专用插件） | 系统安装 `fcitx5-frontend-qt6`，且 Qt 能加载 `libfcitx5platforminputcontextplugin.so` | PySide6 wheel 不包含此插件；Nuitka 打包路径隔离，即使有系统插件也不加载 |
| **B. 原生 Wayland text-input-v3** | Qt ≥ 6.7 + Compositor 支持 v3 + fcitx5 以 Wayland 模式运行 | Qt 6.10 ✓；GNOME/Mutter ✓；但 fcitx5 是否注册 Wayland 前端未知 |

**根因**：

- PySide6 的 pip wheel **从设计上就不包含 fcitx5 平台插件**（ibus 插件内置，fcitx5 需系统包提供）。
- 在 **X11 下**，即使缺少 fcitx5 专用插件，fcitx5 仍可通过 **XIM 协议** 兜底工作。
- 在 **Wayland 下，XIM 完全不可用**。如果 Qt 应用没有 fcitx5 插件，也没有走通 text-input-v3，输入法就**彻底失联**。

- 这也是为什么 CachyOS 上运行源码可能正常：Arch 系通常通过包管理器安装了 `fcitx5-frontend-qt6`，系统 Qt 插件路径包含 `libfcitx5platforminputcontextplugin.so`，运行源码时 Qt 会搜索并加载。

---

## 验证步骤（请按顺序执行）

### 步骤 0：确认环境

```bash
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
echo "QT_QPA_PLATFORM=$QT_QPA_PLATFORM"
echo "QT_IM_MODULE=$QT_IM_MODULE"
fcitx5-diagnose | head -n 30
grep flags /proc/cpuinfo | head -1
```

### 步骤 1：定位 core dump 根因

在低配机器的 `main.bin` 所在目录执行以下命令，**逐一测试**：

```bash
# 测试 A：强制软件渲染，排除 GPU 问题
QT_QUICK_BACKEND=software ./main.bin

# 测试 B：强制 XWayland，排除 Wayland 插件问题
QT_QPA_PLATFORM=xcb ./main.bin

# 测试 C：查看插件加载日志
QT_DEBUG_PLUGINS=1 ./main.bin 2>&1 | head -n 80

# 测试 D：检查 core dump 信号类型（systemd 系统）
coredumpctl info main.bin

# 测试 E：用 gdb 查看栈回溯
gdb ./main.bin core
# 在 gdb 中执行：bt
```

**结果判定：**

| 测试结果 | 根因 | 对应修复 |
|----------|------|----------|
| `QT_QUICK_BACKEND=software` 正常 | GPU/RHI 初始化失败 | 在 `main.py` 中检测并自动 fallback |
| `QT_QPA_PLATFORM=xcb` 正常 | Wayland 插件缺失 | 修改 Nuitka 打包参数 |
| 两者都崩溃 | 更深层问题（如 libc 版本/CPU 指令集） | 需进一步 gdb 分析 |

### 步骤 2：定位输入法问题

```bash
# 测试 A：强制 XWayland + fcitx（workaround 测试）
QT_QPA_PLATFORM=xcb QT_IM_MODULE=fcitx uv run python main.py

# 测试 B：查看 PySide6 是否能找到系统 fcitx5 插件
uv run python -c "
import PySide6, os
base = os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'plugins')
for root, dirs, files in os.walk(base):
    for f in files:
        if 'fcitx' in f.lower():
            print(os.path.join(root, f))
print('--- 系统 Qt 路径 ---')
import subprocess; subprocess.run(['qtpaths6', '--plugin-dir'], capture_output=True)
"

# 测试 C：确认系统是否安装了 fcitx5 Qt6 前端
ls /usr/lib/x86_64-linux-gnu/qt6/plugins/platforminputcontexts/libfcitx5platforminputcontextplugin.so 2>/dev/null || echo "未安装"

# 测试 D：尝试 text-input-v3 原生路径
unset QT_IM_MODULE
QT_QPA_PLATFORM=wayland uv run python main.py
```

**结果判定：**

| 测试结果 | 根因 | 对应修复 |
|----------|------|----------|
| `QT_QPA_PLATFORM=xcb` 下输入法正常 | 需要 XWayland 兜底 | 启动脚本自动 fallback |
| 系统未安装 `fcitx5-frontend-qt6` | 缺少 fcitx5 Qt 插件 | `apt install fcitx5-frontend-qt6` |
| 已安装但 PySide6 找不到 | 插件路径隔离 | 在 `main.py` 中追加 `QT_PLUGIN_PATH` |
| `unset QT_IM_MODULE` + wayland 正常 | text-input-v3 已可用 | 启动时取消 `QT_IM_MODULE` |

---

## 修复方案

### 修复 P1：core dump

根据验证结果选择路径：

#### 路径 1A：GPU fallback（若 `QT_QUICK_BACKEND=software` 验证通过）

在 `main.py` 中 `QGuiApplication` 创建之前加入：

```python
import os

# 检测是否需要强制软件渲染（低配/老旧 GPU 兼容）
def _should_use_software_rendering() -> bool:
    """在检测到可能不兼容的 GPU 环境时启用软件渲染。"""
    # 如果用户已显式设置，尊重用户选择
    if os.environ.get("QT_QUICK_BACKEND"):
        return False
    # 在 Wayland 下且没有显式 GPU 驱动线索时保守 fallback
    # 更精确的检测：通过 glxinfo/vulkaninfo 判断支持的 OpenGL 版本
    try:
        import subprocess
        result = subprocess.run(
            ["glxinfo"], capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            # 检查 OpenGL 核心版本
            for line in result.stdout.splitlines():
                if "OpenGL core profile version string" in line:
                    version_str = line.split(":")[-1].strip().split()[0]
                    major, minor = map(int, version_str.split(".")[:2])
                    if (major, minor) < (3, 3):
                        return True
                    break
    except Exception:
        pass
    return False

if _should_use_software_rendering():
    os.environ["QT_QUICK_BACKEND"] = "software"
    log_info("[main] 检测到老旧 GPU，已启用 Qt 软件渲染")
```

#### 路径 1B：Nuitka 打包加固（若 `QT_QPA_PLATFORM=xcb` 验证通过）

修改 `.github/workflows/build-release.yml` 中的打包参数：

```bash
uv run python -m nuitka main.py \
  --follow-imports \
  --enable-plugin=pyside6 \
  --include-qt-plugins=qml,platforms,platforminputcontexts,platformthemes,wayland-shell-integration,wayland-graphics-integration-client,wayland-decoration-client,xcbglintegrations \
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

### 修复 P2：fcitx5 输入法

#### 方案 A：在 main.py 中显式追加系统 Qt 插件路径（推荐，影响源码运行）

在 `main.py` 顶部、`QGuiApplication` 创建之前：

```python
import os
import PySide6

# 追加系统级 Qt 插件路径，使 PySide6 能找到 fcitx5 等系统插件
_system_qt_plugin_paths = [
    "/usr/lib/x86_64-linux-gnu/qt6/plugins",   # Ubuntu/Debian
    "/usr/lib/qt6/plugins",                     # Arch/Fedora/openSUSE
    "/usr/local/lib/qt6/plugins",
]
_existing_paths = os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep)
_new_paths = [p for p in _system_qt_plugin_paths if os.path.exists(p) and p not in _existing_paths]
if _new_paths:
    os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(_existing_paths + _new_paths)
    log_info(f"[main] 已追加系统 Qt 插件路径: {_new_paths}")
```

#### 方案 B：启动脚本自动 fallback 到 XWayland（最稳兜底）

在 `main.py` 顶部检测 Wayland + 无 fcitx5 插件时，自动切换到 XWayland：

```python
# 输入法兼容性 fallback
if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
    # 检查是否能找到 fcitx5 插件
    qt_plugin_path = os.environ.get("QT_PLUGIN_PATH", "")
    has_fcitx5_plugin = False
    for path in qt_plugin_path.split(os.pathsep) if qt_plugin_path else []:
        if os.path.exists(os.path.join(path, "platforminputcontexts", "libfcitx5platforminputcontextplugin.so")):
            has_fcitx5_plugin = True
            break
    if not has_fcitx5_plugin and not os.environ.get("QT_QPA_PLATFORM"):
        log_info("[main] Wayland 下未检测到 fcitx5 Qt 插件，自动 fallback 到 XWayland")
        os.environ["QT_QPA_PLATFORM"] = "xcb"
```

#### 方案 C：Nuitka 打包时嵌入 fcitx5 插件（最佳发行体验）

在 `.github/workflows/build-release.yml` 中增加步骤：

```yaml
      - name: 安装 fcitx5 Qt6 前端
        run: sudo apt install -y fcitx5-frontend-qt6

      - name: 打包后合并输入法插件
        run: |
          mkdir -p build-src/deployment/main.dist/platforminputcontexts
          cp /usr/lib/x86_64-linux-gnu/qt6/plugins/platforminputcontexts/libfcitx5platforminputcontextplugin.so \
             build-src/deployment/main.dist/platforminputcontexts/ 2>/dev/null || true
        working-directory: build-src
```

> ⚠️ 注意：嵌入的 `.so` 需要与 PySide6 的 Qt 版本严格匹配，否则可能加载失败。建议在 CI 中打印 `qmake6 -query QT_VERSION` 确认版本一致性。

---

## 建议的修复优先级

1. **先验证**（用户侧）：执行上述"验证步骤"，确认具体根因。
2. **再改打包**（无论验证结果）：Nuitka 参数补充 `--include-qt-plugins` 包含 Wayland 相关目录（无害）。
3. **同步改 main.py**：追加系统 Qt 插件路径 + XWayland fallback 逻辑（解决源码运行和打包运行的输入法问题）。
4. **最后考虑嵌入**：如果确认 XWayland fallback 不可接受（比如用户坚持原生 Wayland），再在 CI 中嵌入 fcitx5 插件。

---

## 参考链接

- [Fcitx 5 Wayland 官方文档](https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland)
- [Nuitka Segfault 诊断指南](https://nuitka.net/info/segfault.html)
- [Qt 6 Wayland text-input-v3 支持](https://codereview.qt-project.org/c/qt/qtwayland/+/416862)
