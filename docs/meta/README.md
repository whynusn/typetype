# 文档维护规范

> 面向 AI Agent 和开发者。描述 typetype 文档的结构约定、权威优先级和同步规则。

## 📍 文档导航卡（你在这里）

本文档定义文档职责、权威优先级与同步规则。出现冲突时以本文为准。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 文档规范、权威优先级、同步规则 | [README.md](../README.md) — 快速入门<br>[ARCHITECTURE.md](../ARCHITECTURE.md) — 架构权威<br>[AGENTS.md](../AGENTS.md) — 开发规范 | [文档结构](#文档结构)<br>[权威优先级](#权威优先级)<br>[同步规则](#同步规则) |

---

## 文档结构

```text
typetype/
├── README.md                    ← [人类入口] 项目概述、快速开始
├── AGENTS.md                    ← [AI 入口] 编码规范、已知陷阱（唯一规则源）
├── CLAUDE.md                    ← [Claude 指令] 纯指针→AGENTS.md（零重复内容）
├── docs/
│   ├── ARCHITECTURE.md          ← [宪法] 架构分层、数据流、依赖规则
│   ├── reference/               ← [速查表] 纯表格（配置/API/QML/指标）
│   ├── decisions/               ← [ADR] 架构决策记录（新建，按编号索引）
│   ├── history/                 ← [归档] 历史文档（冻结，不新增）
│   └── meta/                    ← [元规则] 本文档体系规范
└── skills/                      ← [AI 操作手册] 场景驱动
```

## 权威优先级

出现冲突时，按此顺序判断：

1. **当前源码**
2. `ARCHITECTURE.md`
3. `docs/reference/*`
4. `AGENTS.md`
5. `skills/*`
6. `docs/history/*`

## 文档类型定义

| 类型 | 位置 | 面向 | 内容规则 |
|:--- |:--- |:--- |:---|
| 人类入口 | `README.md` | 人类开发者 | 项目概述、快速开始、功能列表。不写编码规则。 |
| AI 规则源 | `AGENTS.md` | AI Agent | 编码规范、已知陷阱、开发约束。**所有 AI 行为规则唯一存放处**。 |
| 工具指令 | `CLAUDE.md` | Claude Code | 纯指针→AGENTS.md，**零项目文档内容**。可有工具特有行为配置（≤15行）。 |
| 事实文档 | `ARCHITECTURE.md` | 所有人 | 架构事实、数据流、依赖规则、设计陷阱。不限行数。 |
| 速查表 | `docs/reference/*` | 开发者/AI | 纯表格，不写教程。每个文件 ≤ 200 行。 |
| ADR | `docs/decisions/*` | 开发者/AI | 架构决策记录。编号索引，标准模板（背景/选项/决策/影响）。 |
| 历史归档 | `docs/history/*` | 参考 | 已完成的设计文档、bug 记录。**冻结，不新增、不修改**。 |
| 操作手册 | `skills/*` | AI Agent | 场景驱动的工作流指令。引用 docs 内容但不复制。 |

## 同步规则

### 代码变更后的文档更新

| 变更类型 | 需要更新 | 原则 |
|:--- |:---|:---|
| 新增/删除/重命名源码文件 | `ARCHITECTURE.md` 目录结构 | 事实 → 宪法 |
| 新增/修改配置字段 | `docs/reference/config.md` | 事实 → 速查表 |
| 新增/删除 QML 页面 | `docs/reference/qml-pages.md` | 事实 → 速查表 |
| 新增/修改 Bridge Slot/Signal | `docs/reference/bridge-slots.md` | 事实 → 速查表 |
| 新增/修改 API 端点 | `docs/reference/api-endpoints.md` | 事实 → 速查表 |
| 发现**编码实践类**陷阱 | `AGENTS.md` § 已知陷阱 | 规则 → AI 规则源 |
| 发现**架构设计类**陷阱 | `ARCHITECTURE.md` § 已知陷阱 | 事实 → 宪法 |
| 架构分层变更 | `ARCHITECTURE.md` 分层架构 + 依赖规则 | 事实 → 宪法 |
| 重大架构决策 | `docs/decisions/` 新建 ADR | 决策 → ADR |
| 完成复杂修复 | 考虑写入 `docs/decisions/` 或 `docs/history/` | 记录 → ADR 或 归档 |

**核心原则**：每类信息只有一处存放。**指向不复制**。

### 验证清单（提交前）

- [ ] `ARCHITECTURE.md` 目录结构与 `src/backend/` 实际文件一致
- [ ] `docs/reference/` 中的表格与代码一致
- [ ] `AGENTS.md` § 已知陷阱 与 `ARCHITECTURE.md` § 已知陷阱 无内容重叠
- [ ] 所有内部链接无断链（相对路径正确）
- [ ] `CLAUDE.md` 不超过 15 行，无项目文档内容
- [ ] `docs/history/` 中没有新增文件（冻结目录）

## 写作风格

- **速查表**：纯表格，H1 标题 + `> ` 摘要行 + 表格主体。不写段落。
- **事实文档**：直接、简洁。先给结论，再给解释。代码块标注语言。
- **禁止**：TODO/占位文本、大段源码复制、在一个文件中混合多个不相关主题。
