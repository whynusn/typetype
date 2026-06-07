# 历史设计文档归档
<!-- 状态: archived -->

> 已完成功能的设计文档、实施计划与 bug 记录。只接收旧资料迁移；归档后正文不再维护。
> 当前架构事实以 [ARCHITECTURE.md](../ARCHITECTURE.md) 为准；架构决策见 [decisions/](../decisions/)。

## 功能设计与实施

| 文档 | 主题 |
|:--- |:--- |
| [2026-04-19-weak-chars-custom-sort](2026-04-19-weak-chars-custom-sort.md) | 薄弱字自定义排序 |
| [2026-04-20-backspace-correction-stats-design](2026-04-20-backspace-correction-stats-design.md) | 回改/退格统计指标 |
| [2026-04-21-slice-typing-design](2026-04-21-slice-typing-design.md) | 载文（分片跟打）功能设计 |
| [2026-04-21-slice-typing-design-v1](2026-04-21-slice-typing-design-v1.md) | 载文分片功能 v1 初版草案 |
| [2026-04-22-session-context-design](2026-04-22-session-context-design.md) | 打字会话状态机（TypingSessionContext） |
| [2026-04-25-score-format-unification-design](2026-04-25-score-format-unification-design.md) | 成绩格式统一与 sliceStatusBar 导航 — 设计 |
| [2026-04-25-score-format-unification](2026-04-25-score-format-unification.md) | 成绩格式统一与 sliceStatusBar 导航 — 实施 |
| [2026-04-26-client-server-score-contract-alignment](2026-04-26-client-server-score-contract-alignment.md) | 客户端与后端成绩指标契约对齐 |
| [ai-agent-plan](ai-agent-plan.md) | AI Typing Coach Agent 改造规划 |
| [jwt-timer-refresh-design](jwt-timer-refresh-design.md) | JWT 定时刷新设计 |
| [keyboard-listener-enhancement](keyboard-listener-enhancement.md) | 键盘设备识别增强与手动选择 |
| [leaderboard-design](leaderboard-design.md) | 文本排行榜设计 |
| [spring-boot-design](spring-boot-design.md) | Spring Boot 后端设计方案 |

## 修复记录

| 文档 | 主题 |
|:--- |:--- |
| [fix-icon-behavior-on-color](fix-icon-behavior-on-color.md) | Icon.qml 移除 Behavior on color |
| [fix-score-upload-summary](fix-score-upload-summary.md) | 成绩上传修复总结 |
| [fix-slice-cursor-and-pass-count](fix-slice-cursor-and-pass-count.md) | 分片 QTextCursor 越界 + 达标次数累计 |
| [ubuntu24-wayland-fcitx5-and-nuitka-coredump](ubuntu24-wayland-fcitx5-and-nuitka-coredump.md) | Ubuntu 24 + Wayland v0.3.7 问题诊断 |

## 待解决问题

| 文档 | 主题 |
|:--- |:--- |
| [unfixed-bugs-2026-04-15](unfixed-bugs-2026-04-15.md) | 未修复 Bug 记录 |
| [unfixed-performance-memory-2026-04-26](unfixed-performance-memory-2026-04-26.md) | 性能与内存问题分析 |
