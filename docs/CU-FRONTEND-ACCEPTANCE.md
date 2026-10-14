# Computer Use 前端验收测试打通报告

日期：2026-10-13
范围：typetype（PySide6+QML 中文打字练习）在 AI agent 全自动化开发中的前端验收环节

---

## 一、问题背景

AI agent 全自动化开发时，原本由人工负责的前端验收测试环节（启动应用 → 点一遍关键路径 →
看状态变化 → 视觉判定）需要工具替代。本机（CachyOS + Hyprland/Wayland）已建成 computer
use（CU）测试栈并打通：

- **helper.py**（`~/.zcode/cua-linux/helper.py`，systemd user 服务）：自建 Linux broker，
  实现 a11y 树遍历（AT-SPI）、元素语义动作、鼠标（缩放校准）、键盘注入、截图（grim）。
- **zcode dist 层**：`agent.computerUse` SDK，Element 动作 / actionable 截图 / list_apps。

typetype 的特殊性：练习输入走 **evdev 全局键盘捕获**（`GlobalKeyListener`，绕过窗口系统），
CU 注入的键事件必须出现在它能看到的 evdev 设备上才算数。初测注入无效，本报告记录根因、
修复与方案分析。

## 二、需求

1. CU 注入的键盘事件能被 typetype 的 evdev 全局捕获看见，走与物理键盘**同一条链路**。
2. 不破坏对真实物理键盘的识别口径（严格/宽松两阶段扫描语义不变）。
3. CU 全流程可验证：a11y 树观察 → 点击聚焦打字区 → 注入按键 → 统计/输入真实变化。
4. 方案对 agent 自动化编排友好（时序确定、可脚本化）。

## 三、根因分析（两个门，先后挡路）

### 门 1：设备分类过滤（已修）

`GlobalKeyListener._is_keyboard_strict/_is_keyboard_permissive` 均排除带 `EV_REL` 的设备
（"有鼠标功能的设备不可能是纯键盘"）。而 ydotool 注入走 `ydotoold virtual device` 这个
**键鼠合一 uinput 设备**（实测 `EV_REL=True`，540 个 EV_KEY 码），被当鼠标过滤 → 注入的键
对 app 不可见。**不是防作弊设计，是设备分类口径与虚拟设备的巧合冲突。**

### 门 2：手动设备选择优先于自动发现（配置修复）

`start()` 中 QSettings 手动设备选择优先，自动发现（含白名单）被跳过。本机
`~/.config/Unknown Organization/main.py.conf` 存有手动选择（Rapoo ×2 + 误选的 HDMI
event20），ydotoold 设备（event21）不在其中 → 白名单依然没机会生效。

### 门 3（非门，验证方法坑）：a11y 统计读回失真

Qt AT-SPI value interface 读回不可靠（app 日志大量 `Could not convert to double:
GetCurrentValue`）。注入后用 a11y 读统计文本显示 "击键: 0.00" 是**假象**；截图看 UI 才是
可靠验证（实测截图显示 击键 0.09 / 用时 33.3 / 输入 "aa" + 拼音候选）。

## 四、可行的解决方式（对比）

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. 纯键盘 uinput 设备（测试侧） | helper 用 evdev `UInput` 造只含 EV_KEY 的设备（无 EV_REL），通过严格扫描 | 不改 app；设备属性可控 | app 只在 `start()` 扫描一次（无热插拔），设备必须先于 app 存在；多一套设备管理 | 备选 |
| B. **app 过滤代码加白名单（本次采用）** | `VIRTUAL_KEYBOARD_WHITELIST` 按设备名跳过 EV_REL/EV_ABS 排除，仍要求 EV_KEY+标准键码 | 测试口径与物理键盘完全同链路；白名单显式可审计；已补单测 | 改了 app（用户已授权）；ydotool 设备同时是鼠标，鼠标按键 BTN 事件也可能被读（>256 码，被既有逻辑忽略） | **最优** |
| C. 手动设备选择追加虚拟设备 | QSettings 追加 ydotoold 路径 | 不改代码 | 依赖手动配置优先级，绕过白名单语义；eventN 路径不稳 | 作为补充（本次实际同时用了） |
| D. app 加测试 seam（调试 IPC/a11y 动作注入键） | 绕过 evdev 直接调 `handlePressed` | 最稳定 | 改变了被测口径（不再测输入链路） | 仅单元测试用（已有 `test_global_key_listener.py`） |

**最优方案 = B + C 组合，A 作为无侵入备选**：白名单让虚拟键盘通过扫描口径；自动化编排里
显式把虚拟设备写入手动选择（或清空选择走自动发现），消除扫描时序依赖。改动最小、口径最真
、可审计。

白名单实现（`src/backend/integration/global_key_listener.py`）：

```python
VIRTUAL_KEYBOARD_WHITELIST = {
    "ydotoold virtual device",
    "cu-virtual-keyboard",   # 方案 A 的纯键盘设备名，预留
}
```

两个谓词中：白名单设备只要求 `EV_KEY in caps` + 存在 <256 的标准键码，跳过
`EV_REL`/`EV_ABS` 排除。配套单测 2 个（白名单命中 / 白名单设备无标准键码仍拒绝），16 全过。

## 五、CU 验收测试标准流程（已验证）

```
1. 前置：app 启动前虚拟键盘设备已存在（ydotoold 常驻；QSettings 选择含 event21
   或清空选择走自动发现+白名单）
2. 启动：QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 QT_ACCESSIBILITY=1 uv run main.py
   （Qt a11y 树必需此环境变量，gsetting 不够）
3. 观察：helper capture_app → a11y 树（70 元素：按钮/统计/输入框带语义与 bounds）
4. 聚焦：helper click {"point":{x,y}}（打字区中心，屏幕坐标）→ 输入框 focused=true
5. 注入：helper press_key {"key":"a"} / ydotool key 30:1 30:0 → 经 event21 进
   GlobalKeyListener → 打字启动
6. 断言：截图看 UI（击键/用时/输入/候选栏）—— 不要用 a11y 读统计文本（失真）
```

**端到端实测结果**：注入后输入区显示 "aa"、拼音候选弹出（"1 了 2 也…"）、击键 0.09、
用时 33.3 计时启动。全链路与物理键盘同路径。

## 六、能力边界与归属权

| 层 | 归属 | 边界 |
|---|---|---|
| helper.py + systemd 服务 | 用户本地自建 | 可自由扩展（如 vk_create/vk_key）；不受 zcode 更新影响 |
| node-repl-host dist（3 个本地补丁） | zcode 官方 | 插件更新会覆盖补丁；边界 = agent.computerUse SDK 面 |
| typetype 过滤代码 | 用户项目 | 本次已加白名单（用户授权）；测试 seam 只进单测 |

CU 能力边界：a11y 观察/元素动作/坐标点击/键盘注入 ✓；QML TextEdit a11y setValue ✗（Qt
限制）；evdev 抓键应用须走本报告的虚拟键盘链路 ✓（已打通）；a11y 读 Qt 统计值 ✗（用截图）。

## 七、遗留事项

1. eventN 设备号会漂移（HDMI event20 曾被误选入手动选择）；建议后续把手动选择迁移到
   by-id 或改用白名单自动发现，并对虚拟设备做名称匹配而非路径匹配。
2. `on_key_received` 的 `_lower_pane_focused` 门要求先点击打字区——CU 编排必须含聚焦步骤。
3. ydotoold 设备是键鼠合一的，鼠标按键（BTN_*，码 >256）事件也会进 handler，被既有
   `k < 256` 键码过滤兜住；如未来支持扩展键码需注意。
4. helper 可加 `vk_create`/`vk_key`（纯键盘 UInput 设备，名 `cu-virtual-keyboard`），
   配合白名单预留名，摆脱对 ydotoold 的依赖（方案 A）。
