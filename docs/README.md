# TypeType 文档中心

> 最后更新：2026-04-03

---

## 文档索引

### 核心文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [developer-architecture-handbook.md](./developer-architecture-handbook.md) | **开发者架构手册** - 当前客户端架构事实、文本加载闭口后的边界规则与协作约束 | ✅ 当前源码事实来源 |
| [guide.md](./guide.md) | **AI Agent 转化规划指南** - 项目规划与方案文档 | ✅ 规划文档 |
| [roadmap.md](./roadmap.md) | **功能路线图** - 当前完成状态与后续规划 | ✅ 规划文档 |
| [spring-boot-backend-design.md](./spring-boot-backend-design.md) | **Spring Boot 后端设计方案** - 服务端方案与集成设想 | ✅ 后端方案文档 |

### 项目根文档

| 文档 | 位置 | 说明 |
|------|------|------|
| AGENTS.md | [../AGENTS.md](../AGENTS.md) | 项目开发指南（架构、代码风格、测试） |
| README.md | [../README.md](../README.md) | 项目概览与快速开始 |

---

## 文档关系

若出现架构描述冲突：

1. 先看当前源码
2. 再看 [developer-architecture-handbook.md](./developer-architecture-handbook.md)
3. 若问题涉及文本加载边界归属，以该手册中的“最终形态”与边界规则为准
4. 其他文档中的架构描述按“规划/历史背景”理解，除非它明确声明自己是当前事实来源

```
┌─────────────────────────────────────────────────────────────┐
│                      TypeType 项目                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   客户端改造   │ │   后端设计    │ │   功能规划    │
│   (guide.md)  │ │ (spring-boot) │ │ (roadmap.md)  │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │    AI Agent 改造    │
                │   面试项目杀手锏    │
                └─────────────────────┘
```

---

## 快速导航

### 我想了解...

#### ...AI Agent 改造方案
→ [guide.md](./guide.md) - 完整的 Agent 架构、技术选型、实施路线

#### ...后端如何设计
→ [spring-boot-backend-design.md](./spring-boot-backend-design.md) - 数据库、API、缓存、安全

#### ...项目当前进度
→ [roadmap.md](./roadmap.md) - 已完成、进行中、待开发功能

#### ...如何开始开发
→ [AGENTS.md](../AGENTS.md) - 开发环境、命令、架构说明

#### ...分层边界与协作规范
→ [developer-architecture-handbook.md](./developer-architecture-handbook.md) - 当前架构判断、目标架构与协作约定

---

## 文档维护规范

### 命名规范
- 英文文件名，小写 + 短横线分隔
- 示例：`spring-boot-backend-design.md` ✅ / `SpringBoot后端设计.md` ❌

### 更新日期
- 每个文档顶部标注 `最后更新：YYYY-MM-DD`
- 重大变更需在文档底部添加 Changelog

### 内容组织
- 每个文档聚焦一个主题
- 避免跨文档重复内容（使用链接引用）
- 代码示例保持与实际代码同步

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-03 | 重写 developer-architecture-handbook.md，明确其为客户端架构事实来源并更新文本加载闭口后的边界规则 |
| 2026-04-03 | 为 guide / roadmap / spring-boot 文档补充“规划文档”定位说明 |
| 2026-03-21 | 新增 developer-architecture-handbook.md（开发者架构手册） |
| 2026-03-21 | 创建文档索引，重命名功能路线图文件 |
| 2026-03-21 | 新增 guide.md（AI Agent 转化规划） |
| 2026-03-19 | 新增 Typetype功能路线图.md |
| 2026-03-15 | 新增 spring-boot-backend-design.md |
