# 文档维护规范
<!-- 状态: active | 最后验证: 2026-05-14 -->

> 面向 AI Agent 和开发者。描述 typetype 文档的结构约定、权威矩阵和同步规则。

## 📍 文档导航卡（你在这里）

本文档定义文档职责、权威矩阵与同步规则。出现冲突时以本文为准。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 文档规范、权威矩阵、同步规则 | [README.md](../../README.md) — 快速入门<br>[ARCHITECTURE.md](../ARCHITECTURE.md) — 架构权威<br>[AGENTS.md](../../AGENTS.md) — 开发规范 | [文档结构](#文档结构)<br>[权威矩阵](#权威矩阵冲突解决)<br>[同步规则](#同步规则) |

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
│   ├── guides/                  ← [操作手册] 任务驱动的步骤指导
│   ├── examples/                ← [代码示例] 独立可运行的示例
│   ├── decisions/               ← [决策] 架构决策记录（新建，按编号索引）
│   ├── history/                 ← [归档] 历史文档（冻结，不新增）
│   ├── superpowers/             ← [规划档案] 既有 specs/plans，作为历史规划材料
│   └── meta/                    ← [元规则] 本文档体系规范
└── CHANGELOG.md                 ← [发布历史] 版本变更记录
```

## 权威矩阵（冲突解决）

当不同文档给出相反信息时，先判断冲突类型，再使用对应优先级链。

### 维度 A：事实可靠性链

用于代码、架构、配置、API、QML 页面等技术事实冲突：

```text
源码 > docs/ARCHITECTURE.md > docs/reference/* > docs/decisions/* > AGENTS.md > docs/guides/* > docs/history/* > docs/superpowers/*
```

### 维度 B：操作优先级链

用于编码规范、禁忌、工作流步骤、验证要求等行为指令冲突：

```text
AGENTS.md > docs/guides/* > docs/ARCHITECTURE.md > docs/decisions/* > docs/reference/* > docs/history/* > docs/superpowers/*
```

### 维度 C：跨维度冲突处理

1. 同一维度内冲突，使用对应优先级链。
2. 跨维度冲突，先阅读源码和相关文档；仍无法判断时询问维护者。
3. 信息不足时不要创作规则，应补充权威源或记录待确认项。

## 文档类型定义

| 类型 | 位置 | 面向 | 内容规则 |
|:--- |:--- |:--- |:---|
| 人类入口 | `README.md` | 人类开发者 | 项目概述、快速开始、功能列表。不写编码规则。 |
| AI 规则源 | `AGENTS.md` | AI Agent | 编码规范、已知陷阱、开发约束。**所有 AI 行为规则唯一存放处**。 |
| 工具指令 | `CLAUDE.md` | Claude Code | 纯指针→AGENTS.md，**零项目文档内容**。可有工具特有行为配置（≤15行）。 |
| 事实文档 | `ARCHITECTURE.md` | 所有人 | 架构事实、数据流、依赖规则、设计陷阱。不限行数。 |
| 速查表 | `docs/reference/*` | 开发者/AI | 纯表格，不写教程。每个文件 ≤ 200 行。 |
| 操作手册 | `docs/guides/*` | 开发者/AI | 任务驱动的步骤、命令、验证方式。引用 docs 内容但不复制。 |
| 代码示例 | `docs/examples/*` | 开发者/AI | 独立可运行示例，展示最佳实践。完整规范指向 reference。 |
| 架构决策记录 | `docs/decisions/*` | 开发者/AI | 架构决策记录。编号索引，标准模板（背景/选项/决策/影响）。 |
| 历史归档 | `docs/history/*` | 参考 | 已完成的设计文档、bug 记录。**冻结，不新增、不修改**。 |
| 规划档案 | `docs/superpowers/*` | 参考 | 既有 specs/plans 材料；不作为当前事实或操作规则的权威来源。 |
| 发布历史 | `CHANGELOG.md` | 用户/维护者 | 版本变更、用户可见改动、破坏性变更。 |

## 分级复制规则

| 级别 | 名称 | 规则 | 标注 | 典型场景 |
|:---|:---|:---|:---|:---|
| L1 | 零复制 | 只链接，不重复描述 | `@see path/to/file` | 默认跨文件引用 |
| L2 | 摘要复制 | 复制 1-3 行关键结论 | `@summary from:path` | AGENTS.md 快速参考 |
| L3 | 快照复制 | 完整复制并标注验证日期 | `@snapshot from:path verified:YYYY-MM-DD` | 稳定规范快照 |

修改规范源时，搜索对应 `@summary from:` 和 `@snapshot from:` 标记；L3 快照超过 3 个月必须重新验证。

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
| 重大架构决策 | `docs/decisions/` 新建架构决策记录 | 决策 → 决策记录 |
| 新增工作流/流程 | `docs/guides/` 新建指南 | 流程 → guide |
| 新增示例 | `docs/examples/` 新建示例 | 示例 → examples |
| 发布版本 | `CHANGELOG.md` | 事件 → 历史 |
| 完成复杂修复 | 考虑写入 `docs/decisions/` 或 `docs/history/` | 记录 → 决策记录 或 归档 |

**核心原则**：每类信息只有一处存放。**指向不复制**。

### 验证清单（提交前）

- [ ] `ARCHITECTURE.md` 目录结构与 `src/backend/` 实际文件一致
- [ ] `docs/reference/` 中的表格与代码一致
- [ ] `AGENTS.md` § 已知陷阱 与 `ARCHITECTURE.md` § 已知陷阱 无内容重叠
- [ ] 所有内部链接无断链（相对路径正确）
- [ ] 所有 `@see`、`@summary from:`、`@snapshot from:` 标记指向有效位置
- [ ] `CHANGELOG.md` 已更新（若涉及用户可见变更）
- [ ] `CLAUDE.md` 保持指针性质，无项目文档内容
- [ ] `docs/history/` 中没有新增常规文档；被归档的历史资料保持冻结

---

## 文档状态标记

所有文档应在 H1 标题后包含状态标记：

```markdown
# 文档标题
<!-- 状态: active | draft | deprecated | archived -->
<!-- 最后验证: YYYY-MM-DD -->
```

| 状态 | 含义 | 操作 |
|:---|:---|:---|
| `active` | 当前有效 | 正常维护 |
| `draft` | 草稿，尚未审核 | 完成后设 active |
| `deprecated` | 已弃用，保留参考 | 添加指向替代文档的链接 |
| `archived` | 已归档，不可编辑 | 冻结 |

## 写作风格

- **速查表**：纯表格，H1 标题 + `> ` 摘要行 + 表格主体。不写段落。
- **事实文档**：直接、简洁。先给结论，再给解释。代码块标注语言。
- **操作手册**：步骤、命令、验证方式齐全；架构背景用链接指向 `ARCHITECTURE.md`。
- **代码示例**：独立可运行，聚焦单一概念，避免复制主项目大段源码。
- **禁止**：TODO/占位文本、大段源码复制、在一个文件中混合多个不相关主题。
