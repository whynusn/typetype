<!-- 状态: active | 最后验证: 2026-06-04 -->
# 架构决策记录

> 记录重要的架构决策及其上下文。每个 ADR 包含：背景、选项、决策、影响。

## 📍 文档导航卡

| 当前文档 | 快速链接 |
|:---|:---|
| **本文** — 架构决策索引 | [AGENTS.md](../../AGENTS.md) — 开发规则<br>[ARCHITECTURE.md](../ARCHITECTURE.md) — 架构权威 |

---

## 索引

| 编号 | 标题 | 日期 | 状态 |
|:---|:---|:---|:---|
| 001 | [统一低内存载文管线](./001-unified-low-memory-text-loading.md) | 2026-05-30 | proposed |
| 002 | [打字会话状态机（TypingSessionContext）](./002-typing-session-context.md) | 2026-06-04 | accepted |
| 003 | [NavView 单实例页面切换](./003-single-instance-page-navigation.md) | 2026-06-04 | accepted |
| 004 | [载文分片机制（Slice Typing）](./004-slice-typing-mechanism.md) | 2026-06-04 | accepted |
| 005 | [文本加载统一走 Worker](./005-all-text-load-via-worker.md) | 2026-06-04 | accepted |
| 006 | [成绩展示格式统一与 sliceStatusBar](./006-score-format-unification.md) | 2026-06-04 | accepted |
| 007 | [回改/退格统计指标](./007-backspace-correction-stats.md) | 2026-06-04 | accepted |

---

## 编写规范

每个 ADR 文件命名为 `NNN-简短标题.md`，包含：

- **标题**：做了什么决策
- **背景**：为什么需要这个决策
- **选项**：考虑了哪些方案
- **决策**：选择了哪个，为什么
- **影响**：对代码库的影响

---

## 历史归档

已完成的功能详细设计文档和实施方案已移至 `docs/history/`。历史设计文档不修改、不删除。

> 历史设计文档和实施方案已归档，详见 `docs/history/`。