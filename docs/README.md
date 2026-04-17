# TypeType 开发者文档中心

> 最后更新：2026-04-17
>
> 本目录面向开发者。**当前源码始终比文档更权威**；若文档与代码冲突，请先相信代码，再回头修文档。

---

## 新开发者建议阅读顺序

1. [DEVELOPING.md](./DEVELOPING.md) —— 先把项目跑起来，知道从哪里下手
2. [ARCHITECTURE.md](./ARCHITECTURE.md) —— 理解当前分层、依赖方向、核心数据流
3. [../AGENTS.md](../AGENTS.md) —— 查仓库级开发约束、已知陷阱、验证要求
4. [roadmap.md](./roadmap.md) —— 了解已完成功能与未来方向（**规划文档，不是事实来源**）
5. [AI_AGENT_PLAN.md](./AI_AGENT_PLAN.md) / [SPRING_BOOT.md](./SPRING_BOOT.md) —— 仅在做对应扩展时阅读

---

## 文档索引

### 核心开发文档

| 文档 | 类型 | 说明 |
|------|------|------|
| [DEVELOPING.md](./DEVELOPING.md) | 上手指南 | 环境搭建、运行、调试、开发流程、提交前检查 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 事实文档 | 当前客户端架构、对象装配、数据流、边界规则 |
| [roadmap.md](./roadmap.md) | 规划文档 | 当前功能状态、路线图、后续设想 |

### 扩展方案文档

| 文档 | 类型 | 说明 |
|------|------|------|
| [AI_AGENT_PLAN.md](./AI_AGENT_PLAN.md) | 规划文档 | AI Typing Coach / LangGraph 方向改造方案 |
| [SPRING_BOOT.md](./SPRING_BOOT.md) | 规划文档 | Spring Boot 服务端设计与客户端接入思路 |

### 根目录补充文档

| 文档 | 位置 | 说明 |
|------|------|------|
| [README.md](../README.md) | 仓库根目录 | 面向用户/访客的项目概览 |
| [AGENTS.md](../AGENTS.md) | 仓库根目录 | 仓库级开发约束、验证要求、已知陷阱 |
| [CLAUDE.md](../CLAUDE.md) | 仓库根目录 | Claude Code 协作说明 |

---

## 文档权威优先级

出现冲突时，按下列顺序判断：

1. **当前源码**
2. [ARCHITECTURE.md](./ARCHITECTURE.md)
3. [DEVELOPING.md](./DEVELOPING.md)
4. 其他 `docs/*.md` 规划文档
5. 历史文档 / 聊天记录 / 旧方案草稿

---

## 当前这套文档已对齐的事实（2026-04-17 校验）

- 启动与依赖注入入口：`main.py`
- 当前客户端事实架构：`src/backend/{presentation,application,domain,ports,integration,infrastructure}`
- 当前 QML 入口：`src/qml/Main.qml`
- 当前主功能页：`TypingPage.qml`、`WeakCharsPage.qml`、排行榜页、`ProfilePage.qml`、`SettingsPage.qml`
- 当前 CI 工作流名称：`ci.yml`、`multi-platform-tests.yml`、`build-release.yml`
- 当前文本加载主链路：`Bridge -> TextAdapter -> LoadTextUseCase -> TextSourceGateway`

---

## 你可能最常用的入口

- 想跑项目：看 [DEVELOPING.md#快速开始](./DEVELOPING.md#快速开始)
- 想知道改哪个层：看 [ARCHITECTURE.md#修改一个功能时怎么判断改哪里](./ARCHITECTURE.md#修改一个功能时怎么判断改哪里)
- 想查文本加载流程：看 [ARCHITECTURE.md#文本加载链路](./ARCHITECTURE.md#文本加载链路)
- 想查打字统计陷阱：看 [DEVELOPING.md#高频坑位](./DEVELOPING.md#高频坑位)
- 想查仓库级硬约束：看 [../AGENTS.md](../AGENTS.md)

---

## 文档维护约定

- 先改代码，再同步文档；**架构变更必须同步更新 `ARCHITECTURE.md`**
- 新开发者第一次阅读应能在 10 分钟内回答：
  - 程序从哪里启动？
  - QML 如何调用 Python？
  - 文本加载走哪条链路？
  - 新功能应该放在哪一层？
- 不为“看起来更规范”而随意重命名文档；优先保证链接稳定、内容准确
- 规划类文档必须显式标注“不是当前实现事实来源”

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-06 | 基于当前源码重新校验索引、修正失效链接、补充新开发者阅读顺序 |
| 2026-04-03 | 重写 ARCHITECTURE，明确其为客户端架构事实来源 |
| 2026-03-21 | 创建文档索引 |
