# ADR-015: 前端验收自动化工具（UI Acceptance Harness，AI-agent 亲和）

<!-- 状态: accepted | 决策日期: 2026-10-14 | 最后验证: 2026-10-14 -->

> 实施状态（2026-10-14，P0）：**决策 1-6 已接受，P0 冒烟层已落地**。`tools/ui_probe/`（离屏加载器 + 消息捕获 + ast 解析 bridge API 的 mock bridge 自动生成 + fixtures 属性注入 + 结构化报告）+ `tests/ui_probe/`（pytest 冒烟，含检测器自检）已进入全量测试；CI 经既有 `multi-platform-tests.yml` 覆盖。P1-P3 见「分期」。

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

### 6. 场景 DSL 约束

YAML 声明式（`load / click / type / wait / assert / screenshot`），**只引用 a11y 语义**（objectName / 文本 / role），不 import 任何 typetype 或 RinUI 类型——这是通用性与 AI 可编写性的关键。场景文件即文档，可评审、可 diff。

## 分期

| 期 | 内容 | 状态 |
|:---|:---|:---|
| P0 | 冒烟：离屏加载全部页面/组件 + 消息捕获（加载错误/绑定环/qWarning）+ mock bridge 自动生成（ast 解析 bridge API + 保真默认值）+ fixtures 属性注入 + pytest/CI 接入（子进程隔离） | ✅ 本次落地 |
| P1 | 场景 DSL v0 + 离屏交互（Qt 事件注入）+ a11y 语义树序列化 + `ui_report.json` v1 + typetype 核心流程场景 | 计划 |
| P2 | 重轨 E2E：封装 CU 协议 → xvfb + 虚拟键鼠 + grim，CU 标准流程固化为场景，黄金基线库 | 计划 |
| P3 | 通用化：核心抽独立包/仓 + 文档发布，typetype 只留场景库 | 计划 |

## 影响

- **测试体系**：新增 `tests/ui_probe/`（轻轨，子进程隔离跑 `tools/ui_probe/`）。既有 `tests/test_qml_pages.py`（正则静态断言）与 mock 生成器（ast 解析）各自独立解析同一 bridge API 面，后续可收敛为单一事实源。
- **CI**：无需新增 job（轻轨随全量 pytest）；重轨上线时新增 nightly job。
- **文档**：`AGENTS.md` §4 测试策略补充前端验收分层；`docs/reference/` 增补 harness 使用速查（P1）。
- **CU 资产**：`docs/CU-FRONTEND-ACCEPTANCE.md` 标记为「已被 ADR-015 重轨继承」的历史验证报告。
