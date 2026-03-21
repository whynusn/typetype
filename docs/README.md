# TypeType 文档中心

> 最后更新：2026-03-21

---

## 文档索引

### 核心文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [developer-architecture-handbook.md](./developer-architecture-handbook.md) | **开发者架构手册** - 分层边界、依赖规则、开发流程与协作规范 | ✅ 活跃 |
| [guide.md](./guide.md) | **AI Agent 转化规划指南** - 面试项目改造完整方案 | ✅ 活跃 |
| [roadmap.md](./roadmap.md) | **功能路线图** - 当前完成状态与后续规划 | ✅ 活跃 |
| [spring-boot-backend-design.md](./spring-boot-backend-design.md) | **Spring Boot 后端设计方案** - 服务端架构设计 | ✅ 活跃 |

### 项目根文档

| 文档 | 位置 | 说明 |
|------|------|------|
| AGENTS.md | [../AGENTS.md](../AGENTS.md) | 项目开发指南（架构、代码风格、测试） |
| README.md | [../README.md](../README.md) | 项目概览与快速开始 |

---

## 文档关系

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
→ [developer-architecture-handbook.md](./developer-architecture-handbook.md) - 面向开发者的详细架构手册

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
| 2026-03-21 | 新增 developer-architecture-handbook.md（开发者架构手册） |
| 2026-03-21 | 创建文档索引，重命名功能路线图文件 |
| 2026-03-21 | 新增 guide.md（AI Agent 转化规划） |
| 2026-03-19 | 新增 Typetype功能路线图.md |
| 2026-03-15 | 新增 spring-boot-backend-design.md |
