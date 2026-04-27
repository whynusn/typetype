# 键盘设备识别增强与手动选择功能

**日期**: 2026-04-27
**状态**: 已实现

---

## 背景

Wayland 显示协议下，`GlobalKeyListener` 通过 evdev 监听全局按键事件。蓝牙键盘在某些 Wayland 环境中无法被自动识别，原因可能包括：

- 蓝牙键盘的 `capabilities()` 包含 `EV_ABS`（部分带触摸条的键盘），被严格模式排除
- 权限问题（用户不在 input 组）
- Wayland 合成器对 evdev 设备访问的限制

## 方案：双管齐下

### 1. 增强自动识别

**文件**: `src/backend/integration/global_key_listener.py`

旧代码只有单一 `_is_keyboard()` 方法，使用严格规则（排除 `EV_REL` + `EV_ABS`，要求标准键码）。

新代码改为**两阶段扫描**：

| 阶段 | 方法 | 规则 | 适用场景 |
|------|------|------|----------|
| 严格 | `_is_keyboard_strict` | `EV_KEY` + 排除 `EV_REL` + 排除 `EV_ABS` + 标准键码 | 标准 USB/PS2 键盘 |
| 宽松 | `_is_keyboard_permissive` | `EV_KEY` + 排除 `EV_REL` + 标准键码（不排除 `EV_ABS`） | 蓝牙键盘、带触摸条的键盘 |

**扫描流程**：
1. 先严格扫描 — 找到键盘则直接返回
2. 严格模式未找到 → 切换到宽松模式重扫
3. 仍未找到 → 输出诊断日志（列出所有 `/dev/input/event*` 设备及其分类）→ 抛出 `RuntimeError`

同时新增 `_classify_device()` 方法，将设备分为 `keyboard` / `mouse` / `touchpad/gamepad` / `non-keyboard` / `ambiguous` / `unknown` 等类型，用于诊断日志和 UI 展示。

### 2. 手动设备选择

用户在设置页中可以直接查看和选择要监听的输入设备。

**持久化**：使用 `QSettings` 存储手动选择的设备路径列表。键名：`key_listener/device_paths`。

**API**：

| 方法 | 用途 |
|------|------|
| `get_selected_device_paths()` | 读取 QSettings 中的手动设备路径 |
| `set_selected_device_paths(paths)` | 写入 QSettings |
| `has_selected_devices()` | 判断是否启用了手动选择 |
| `restart_with_selection(paths)` | 停止监听 → 保存选择 → 使用指定设备重启 |
| `restart_auto_detect()` | 停止监听 → 清除手动选择 → 自动发现重启 |

**启动流程（`start()` 方法）**：
1. 检查是否有手动选择的设备路径（QSettings）
2. 有 → 尝试打开这些设备
3. 打开的键盘为空 → 回退到自动发现
4. 自动发现也失败 → 输出诊断信息并报错

### 3. UI（设置页）

在 `SettingsPage.qml` 新增「键盘设备」卡片：

- 列出所有输入设备（路径、名称、类型标签）
- 键盘类型的设备显示绿色类型标签，其他显示灰色
- 每个设备带 `CheckBox`，选中后实时切换
- 选择变更加载到 `GlobalKeyListener.restart_with_selection()`
- 「恢复自动发现」按钮清除手动选择并重启自动扫描
- 「刷新设备列表」按钮重新扫描系统设备

`Bridge` 新增：

| Slot/Property | 用途 |
|---------------|------|
| `listAvailableInputDevices()` | 返回带 `is_keyboard`/`selected` 标记的设备列表 |
| `hasManualKeyboardDevices` (Property) | QML 侧查询是否启用手动选择 |
| `setKeyboardDevices(paths)` | 设置设备并重启监听器 |
| `resetKeyboardAutoDetect()` | 回归自动发现 |
| `keyboardDevicesChanged` (Signal) | 设备选择状态变化时通知 QML |

## 修改文件清单

| 文件 | 修改 |
|------|------|
| `src/backend/integration/global_key_listener.py` | 重构：两阶段扫描（严格+宽松）、`_classify_device()`、手动设备选择（QSettings）、`get_all_devices()`、`restart_with_selection/restart_auto_detect` |
| `src/backend/ports/key_listener.py` | 协议新增 `get_all_devices`、`get_selected_device_paths`、`set_selected_device_paths`、`has_selected_devices`、`restart_with_selection`、`restart_auto_detect` |
| `src/backend/integration/mac_key_listener.py` | 新增协议方法的空实现（macOS 无设备枚举） |
| `src/backend/presentation/bridge.py` | 新增 `keyboardDevicesChanged` 信号、`listAvailableInputDevices` Slot、`hasManualKeyboardDevices` Property、`setKeyboardDevices`/`resetKeyboardAutoDetect` Slot |
| `src/qml/pages/SettingsPage.qml` | 新增「键盘设备」设置卡片 |

## 验证

- 自动发现：严格模式 → 宽松模式 → 回退报错
- 手动选择：CheckBox 勾选 → `restart_with_selection` → 仅指定设备接收按键
- 恢复自动：清除 QSettings → `restart_auto_detect` → 重新扫描
- macOS：新方法空实现，不影响现有功能
- 持久化：重启应用后手动选择配置保持
