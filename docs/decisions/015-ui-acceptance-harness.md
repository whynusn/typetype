# ADR-015: 前端验收自动化工具（UI Acceptance Harness，AI-agent 亲和）

<!-- 状态: accepted | 决策日期: 2026-10-14 | 最后验证: 2026-10-15 -->

> 实施状态（2026-10-15，P0-P1 完成）：**决策 1-6 已接受，P0 冒烟层 / P1.1 快照 / P1.2 场景 DSL / P1.3 真机验收全部落地**。`tools/ui_probe/`（离屏加载器 + 消息捕获 + ast 解析 bridge API 的 mock bridge 自动生成 + fixtures 属性注入 + 结构化快照 + 真机验收 + 场景 DSL + 静态规则 + 一键套件）+ `tests/ui_probe/`（pytest 门禁，含四处检测器自检）已进入全量测试；CI 经既有 `multi-platform-tests.yml` 覆盖。P2-P3 见「分期」。

> 本 ADR 与 [ADR-013](./013-converge-to-three-repo-model.md)（三仓模型）、[ADR-014](./014-ota-update-check-and-mirror-download.md)（OTA）正交，独立评审与排期。核心结论：**自研一套寄居 typetype 仓、按通用核心设计的前端验收 harness——离屏/整机双轨驱动、声明式场景、结构化断言为主黄金像素基线为辅、`ui_report.json` 作为 AI agent 的唯一反馈接口**。

## 背景

现状事实（2026-10-14 核验）：

1. **开发闭环断裂在前端**：本项目大量由 AI agent 开发。后端有 pytest（1235 测试）+ 结构化日志，AI 可自反馈；前端的可视化效果、布局、交互对 AI 不可读——只能读代码猜，或看截图（不可 diff、不可断言、不精确）。
2. **现有手段的缺口**（均为实测）：
   - `tests/test_qml_pages.py` 是**静态文本断言**（正则比对 QML 源码与 bridge API），抓不到运行时问题；
   - `qmllint` 抓不到 RinUI 模块外的未解析类型——PR #50 的 `ItemDelegate is not a type` 整页加载失败由**运行时日志**才发现；
   - QML 绑定环等警告只出现在日志里，**无任何自动化断言**拦截（SettingsPage Switch 绑定环实测）；
   - 视觉验收无黄金基线、无回归比对。
3. **原型已验证存在**：`docs/CU-FRONTEND-ACCEPTANCE.md` 的 CU 栈（helper.py a11y 树遍历 / ydotool 虚拟键盘 evdev 注入 / grim 截图）已打通「全自动化前端验收」链路，但散落在用户本地 `~/.zcode/`，靠人驱动、无声明式场景、无结构化报告。
4. **参照物**：Rust `slint-view`（即时渲染预览 + 错误高亮，面向人眼）、Qt 工具链（`qmllint` 静态 / `qml` 运行时 / Squish 商业 GUI 测试 / GammaRay 内省）。共同缺口：**没有为 AI agent 设计的结构化、脚本化、可断言的验收反馈环**。

**目标**：AI agent 开发前端时，能像跑 pytest 一样跑前端验收，拿回 `ui_report.json`（纯文本、可 grep、可 diff），并有一套持续完善的前端交互与可视化效果测试集兜底。

## 选项

| 方案 | 描述 | 判断 |
|:---|:---|:---|
| A. 商业 GUI 测试（Squish 等） | 成熟的录制回放 + 对象映射 | ❌ 闭源许可与项目三仓去中心化定位冲突；报告非 AI 亲和；场景即代码，AI 不易读改 |
| B. 截图 + 多模态 AI 判读 | agent 自己看截图判断 | ❌ 不可 diff、不可断言、不进 CI；CU 报告已实测 Qt AT-SPI value 读回不可靠，纯视觉口径噪声大 |
| C. 自研分层 harness（本方案） | 离屏/整机双轨 + 声明式场景 + 结构化报告 | ✅ 选中：与项目 AI-agent 开发模式同构；核心可通用；P0 两天内即可抓住实测的两类回归 |
| D. 等待上游工具演进 | 观望 Qt/PySide 生态 | ❌ 无满足「AI 亲和结构化反馈」的现存项，无限期 |

## 决策

### 1. 寄居与通用性的平衡

工具寄居 typetype 仓（`tools/ui_probe/` + `tests/ui_probe/`），但**核心按通用设计**：驱动抽象（`load / find / act / snapshot` 接口）、场景 DSL、报告 schema 均与具体 app 解耦；RinUI/typetype 特定知识（主题 token、桥 API 形态、场景库）放 project adapter / 场景目录，不进核心。P3 评估抽独立仓发布。

### 2. 双轨驱动

- **轻轨**：离屏组件实例（`QT_QPA_PLATFORM=offscreen`，无显示服务器，毫秒级）。承担：页面/组件冒烟加载（加载错误、QML 警告、绑定环）、结构/属性/几何断言、组件级交互（Qt 事件注入）。
- **重轨**：整机 E2E（xvfb + 虚拟键鼠 evdev 注入 + 真实渲染 + a11y 树 + grim 截图）。承担：全链路交互、视觉黄金基线。
- **CU 栈关系**：先**封装** helper.py 协议（吃现成、快），稳定后**内建**（工具自带 xvfb + evdev 驱动，去掉外部依赖）。`docs/CU-FRONTEND-ACCEPTANCE.md` 作为重轨的需求与验证报告归档。

### 3. 视觉验收：结构化断言为主，黄金像素基线为辅

主力断言 = a11y 语义树 + 属性快照（直接读 QML 属性，绕开 AT-SPI value 读回不可靠的问题）+ 几何/颜色/可见性/文本；像素 diff 仅用于少量关键视觉的黄金基线，且容忍度可调。理由：像素对 AI 不友好（噪声大）且脆（字体/动画/主题抖动）；结构化输出可 diff、可定位、可精确归因。

### 4. 输出契约：`ui_report.json` 是 AI agent 的唯一消费接口

schema 版本化（`ui-probe/report@1`），内容：目标清单、加载错误（类型/消息/行号）、QML 警告、a11y 语义树、属性快照、截图路径、黄金基线差异摘要、汇总计数。**纯文本可读、可 grep、可 diff**——这是「AI 亲和」的落地定义。

### 5. 形态与 CI 集成

pytest 插件形态（仓库内 `tools/ui_probe/`，`tests/ui_probe/` 提供 pytest 入口），复用既有 pytest-qt 基建（无显示环境自动 offscreen）。CI：轻轨随全量 pytest 必跑（既有 `multi-platform-tests.yml` 已覆盖）；重轨因依赖显示/键鼠注入，按需或 nightly。

> P0 落地补记（2026-10-14）：
> - **mock bridge 保真度**是零警告基线的前提：bridge API 用 `ast` 解析（正则会被行尾注释整行漏抓信号）；list/QVariantList 属性默认 `[]`（QML 直读 `.length`）；Slot 按返回注解生成类型化默认值（空函数返回 undefined 会触发 "Cannot assign [undefined] to QString"）。
> - **fixtures 属性注入**（`tools/ui_probe/fixtures.json`）：依赖父级状态的组件（如 FontManagerDialog 的 `fontModel`，真实运行时由 SettingsPage 传 ListModel）孤立加载时为 null——显式声明注入而非掩口噪声。支持 `$listmodel` / `$qml` / JSON 原语；key 失配由测试兜底。
> - **子进程隔离**：冒烟跑在独立 python 进程（报告经 JSON 回传）。Qt/shiboken 在主测试进程初始化后，退出期静态析构会与后台 daemon 线程（OTT 跨仓测试的 socketserver）冲突致 SIGABRT——实测全量 pytest 100% 后崩溃，隔离是唯一可靠解。
> - **平台选择走 argv `-platform offscreen`**而非 `QT_QPA_PLATFORM`：用户桌面环境常预置 wayland/xcb，环境变量方案会被预置值赢定。
> - **门禁**：加载失败 / 绑定环 / 零警告（新警告按回归处理）/ 发现覆盖度 / fixture key 有效性 / 绑定环检测器自检（合成已知环，防检测机制静默失效）。
> - **覆盖边界**：经 appBridge 往返的绑定环（`checked → setX → XChanged → 绑定重算`）需真实初始值≠QML 默认值才会在加载期显形，被动 mock 复现不了——归 P1 场景驱动（种子状态 + 交互）解决。

> P1.1/P1.3 落地补记（2026-10-14）：
> - **结构化快照**（`tools/ui_probe/snapshot.py`，`ui-probe/snapshot@1`）：遍历 QQuickItem 树，输出 type/objectName/path/几何(场景坐标)/visible/enabled/text + 选定属性。踩坑：① 类型名带引擎后缀（`WeakCharsPage_QMLTYPE_92`→归一化）；② **objectName 绝大多数为空**，选择器只能靠 type+text+path；③ 离屏无窗口，根节点须显式设视口尺寸（默认 1280×800）布局才解算；④ **QQmlComponent 析构会连带删除它创建的对象**——组件必须与实例同生命周期。全量 33 目标 12597 节点，默认紧凑 JSON（缩进版约 40MB）。
> - **真机验收**（`tools/ui_probe/app_run.py`，`ui-probe/app-run@1`）：复用 `main.bootstrap()` 起真实客户端（真 Bridge/真配置/真数据/真 worker），跑一段事件循环后快照窗口树并捕获 QML 消息。为此把 `main.py` 的启动序列抽成 `bootstrap()/shutdown()`（可测性重构，行为不变）——自动化拿到 engine/window 句柄而不会被 `app.exec()` 阻塞。测试用临时 HOME 隔离真实用户配置（注意：真机启动会往 HOME 拷字体数 MB，不能放小 tmpfs）。
> - **真机首日即抓到两个真实缺陷**（mock 冒烟抓不到）：① 无 keyring 后端的机器上 `create_infra` 抛 `NoKeyringError` 导致**客户端完全起不来**——凭据是可选能力，改为优雅降级；② 已拔出/换过 USB 口的键盘设备以 ERROR 刷屏（可恢复场景），按 errno 降级为带提示的 WARNING。

> P1.2 落地补记（2026-10-15）：
> - **场景引擎**（`tools/ui_probe/scenario.py`，`ui-probe/scenario@1`）：YAML 声明式场景（`wait / assert / click / type / key / call / set / snapshot / pump`），可跑 `app`（真实客户端，复用 `bootstrap()`）或 `component`（隔离组件 + mock bridge）两种模式。选择器只认 a11y 语义（`objectName`/类型/文本/索引路径），不 import 任何 typetype 或 RinUI 类型——为此给 `UpperPane`/`LowerPane` 的 TextArea 补了 `objectName`（`textScreen` / `typingInput`），——这是 harness 反哺产品代码的第一步。
> - **离屏交互**：PySide6 没绑 `QTest` 的 QQuickItem 重载，只能自己注入事件。两条路径都验证可用：`QKeyEvent`（`KeyPress`/`KeyRelease`）与 `QInputMethodEvent`（输入法 commit——中文上屏必需）。调用 QML 函数必须走 `QMetaObject.invokeMethod` + `Q_ARG("QVariant", v)` / `Q_RETURN_ARG(QVariant, ret)`（**类型名要给字符串**），Python 的 `@Slot` 则直接取 Python 属性以免丢失原生返回类型。
> - **消息捕获的盲区（最危险的假阴性）**：App 启动时 `install_qt_message_handler()` 会顶掉 harness 的 Qt handler——**之前"0 警告"的报告是假的**。修法：`install()` 保存前一个 handler，`bootstrap()` 之后 `reinstall()` 夺回并转发；bootstrap 期间的窗口用 Python `logging` sink 兜底；进程退出期的 Qt 消息（此时 handler 已卸载）从子进程 stderr 兜底解析（抓住了 `QThread: Destroyed while thread is still running`）。
> - **每个 app 模式场景跑独立子进程**：进程内起第二个真实客户端会串状态；`run_scenario_isolated` 的子进程必须带 `--no-isolate`（否则无限递归 fork，实测挂死）。
> - **防"永远绿灯"**：`--selfcheck` 合成必然失败的场景，断言引擎确实报失败；汇总判定 `build_ui_report()` 做成纯函数，测试喂脏数据验证它会判 FAIL。
> - **静态规则**（`lint.py`）：`Connections` 内引用 `Window.window` 这类 Item 附加属性——类型检查合法，qmllint 抓不到，运行时每次信号分发报一次（实测一轮打字 **986 条**警告）。规则进 pytest 门禁后，顺手修掉 `TypingPage.qml`（3 处）与 `TextLoadHubPage.qml`（1 处）。
> - **真机沙箱必须连 XDG 一起隔离**（`env.py`）：只设 `HOME` **隔离不住**——桌面会话普遍预置 `XDG_CONFIG_HOME`/`XDG_DATA_HOME`，Qt 与 platformdirs 优先读它们，验收会直接把打字历史写进用户真实目录（本机实测污染了 `~/.local/share/typetype/typing_history.json` 与 `typing_totals.json`）。现在四个 XDG 目录全部指向一次性 HOME，并顺带关闭 QML 磁盘缓存（每次运行几十个文件，还可能拿陈旧缓存掩盖编译错误）；回归门禁见 `tests/ui_probe/test_isolation.py`。

### 6. 场景 DSL 约束

YAML 声明式（`load / click / type / wait / assert / screenshot`），**只引用 a11y 语义**（objectName / 文本 / role），不 import 任何 typetype 或 RinUI 类型——这是通用性与 AI 可编写性的关键。场景文件即文档，可评审、可 diff。

## 分期

| 期 | 内容 | 状态 |
|:---|:---|:---|
| P0 | 冒烟：离屏加载全部页面/组件 + 消息捕获（加载错误/绑定环/qWarning）+ mock bridge 自动生成（ast 解析 bridge API + 保真默认值）+ fixtures 属性注入 + pytest/CI 接入（子进程隔离） | ✅ 已落地 |
| P1.1 | **结构化快照**（`ui-probe/snapshot@1`）：QQuickItem 树 + 属性/几何/可见性，全量目标快照门禁 | ✅ 已落地 |
| P1.3 | **真机验收**（`ui-probe/app-run@1`）：真实客户端（真 Bridge/真配置/真数据）离屏启动 + 窗口快照 + 消息捕获 | ✅ 已落地 |
| P1.2 | 场景 DSL v0 + 离屏交互（Qt 事件注入）+ typetype 核心流程场景 + `ui_report.json` v1 | ✅ 已落地 |
| P2 | 重轨 E2E：封装 CU 协议 → xvfb + 虚拟键鼠 + grim，CU 标准流程固化为场景，黄金基线库 | 计划 |
| P3 | 通用化：核心抽独立包/仓 + 文档发布，typetype 只留场景库 | 计划 |

## 影响

- **测试体系**：新增 `tests/ui_probe/`（轻轨，子进程隔离跑 `tools/ui_probe/`）。既有 `tests/test_qml_pages.py`（正则静态断言）与 mock 生成器（ast 解析）各自独立解析同一 bridge API 面，后续可收敛为单一事实源。
- **CI**：无需新增 job（轻轨随全量 pytest）；重轨上线时新增 nightly job。
- **文档**：`AGENTS.md` §4 测试策略补充前端验收分层；`docs/reference/` 增补 harness 使用速查（P1）。
- **CU 资产**：`docs/CU-FRONTEND-ACCEPTANCE.md` 标记为「已被 ADR-015 重轨继承」的历史验证报告。
