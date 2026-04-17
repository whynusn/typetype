# 文档维护规范

> 面向 AI Agent 和开发者。描述 typetype 文档的结构约定、权威优先级和同步规则。

## 文档结构

```text
typetype/
├── ARCHITECTURE.md              ← 唯一事实来源（"宪法"）
├── AGENTS.md                    ← AI Agent 规则和已知陷阱
├── docs/
│   ├── reference/               ← 速查表（配置/QML/API）
│   ├── history/                 ← 历史归档（AI 一般不读）
│   └── meta/                    ← 本文件（文档规范）
└── skills/                      ← AI 操作手册
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
|------|------|------|---------|
| 事实文档 | `ARCHITECTURE.md` | 所有人 | 代码事实、架构约束、数据流、陷阱。不限行数。 |
| Agent 规则 | `AGENTS.md` | AI Agent | 开发约束、已知陷阱、验证要求、提交前检查。 |
| 速查表 | `docs/reference/*` | 开发者/AI | 纯表格，不写教程。每个文件 ≤ 200 行。 |
| 历史归档 | `docs/history/*` | 参考 | 完成的设计文档、bug 记录。不修改、不删除。 |
| 操作手册 | `skills/*` | AI Agent | 工作流指令（什么场景→查什么文档）。不复制 docs 内容。 |

## 同步规则

### 代码变更后的文档更新

| 变更类型 | 需要更新 |
|---------|---------|
| 新增/删除/重命名源码文件 | `ARCHITECTURE.md` 目录结构 |
| 新增/修改配置字段 | `docs/reference/config.md` |
| 新增/删除 QML 页面 | `docs/reference/qml-pages.md` |
| 新增/修改 Bridge Slot/Signal | `docs/reference/bridge-slots.md` |
| 新增/修改 API 端点 | `docs/reference/api-endpoints.md` |
| 发现新的陷阱/坑位 | `ARCHITECTURE.md` 已知陷阱 或 `AGENTS.md` |
| 架构分层变更 | `ARCHITECTURE.md` 分层架构 + 依赖规则 |
| 新增功能或完成修复 | 考虑是否写入 `docs/history/` 作为记录 |

### 验证清单（提交前）

- [ ] `ARCHITECTURE.md` 目录结构与 `src/backend/` 实际文件一致
- [ ] `docs/reference/` 中的表格与代码一致
- [ ] `ARCHITECTURE.md` 中的陷阱是否覆盖最新发现
- [ ] 所有内部链接无断链（相对路径）
- [ ] `docs/history/` 中没有未完成的文档（除非标题标注"活跃"）

## 写作风格

- **速查表**：纯表格，H1 标题 + `> ` 摘要行 + 表格主体。不写段落。
- **事实文档**：直接、简洁。先给结论，再给解释。代码块标注语言。
- **禁止**：TODO/占位文本、大段源码复制、在一个文件中混合多个不相关主题。
