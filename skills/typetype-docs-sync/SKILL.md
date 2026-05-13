# 文档同步操作手册

> 在大量代码修改或重构后，使文档与代码保持一致。

## 触发方式

在对话中说：

> **"同步文档"** 或 **"sync docs"**

AI Agent 应执行本手册的全部步骤。

---

## 同步流程

### 第 1 步：识别变更范围

```bash
# 查看当前分支与 main 的差异（文件级）
git diff main...HEAD --stat

# 查看具体变更内容
git diff main...HEAD
```

分类变更类型：

| 变更 | 涉及文档 |
|:---|:---|
| 新增/删除/重命名 Python 源文件 | `ARCHITECTURE.md` § 目录结构 |
| 新增/删除 QML 页面 | `docs/reference/qml-pages.md` |
| 修改 Bridge Slot/Signal | `docs/reference/bridge-slots.md` |
| 修改 API 端点 | `docs/reference/api-endpoints.md` |
| 新增配置字段 | `docs/reference/config.md` |
| 新增编码陷阱 | `AGENTS.md` § 已知陷阱 |
| 新增架构决策 | `docs/decisions/` 新建 ADR |
| 架构/分层变更 | `ARCHITECTURE.md` 相关章节 |

### 第 2 步：更新对应文档

**原则**：指向不复制。如果需要引用另一个文档的信息，用链接，不要复制内容。

### 第 3 步：验证

验证清单见 [`docs/meta/README.md § 验证清单`](../../docs/meta/README.md#验证清单提交前)。

```bash
# 关键检查：所有链接有效
# 现有技巧：用编辑器打开 affected .md 文件，点击链接验证

# CLAUDE.md 必须 ≤15 行
wc -l CLAUDE.md  # 应 ≤15

# AGENTS.md 和 ARCHITECTURE.md 陷阱无重叠
# 人工检查：AGENTS.md §8 是编码实践类，ARCHITECTURE.md §已知陷阱 是架构设计类
```

### 第 4 步：提交

文档更新与代码修改应在**同一个 PR/提交**中。

---

## 典型场景

### 场景：重构后同步

```
用户："同步文档"
AI：执行上述 1-4 步
```

### 场景：新增功能后同步

```
用户：feat: 新增 xxx 功能，同步文档
AI：执行上述 1-4 步
```
