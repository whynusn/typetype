# 操作指南

常见任务的分步指导。每个指南都应聚焦一个可执行工作流，并链接到 `docs/reference/` 或 `docs/examples/` 中的权威材料。

---

## 快速导航

| 指南 | 说明 |
|:---|:---|
| 开发环境 | 见 [README.md § 快速开始](../../README.md#快速开始) 与 [AGENTS.md § 开发环境与命令](../../AGENTS.md#1-开发环境与命令) |
| 测试与检查 | 见 [AGENTS.md § 测试策略](../../AGENTS.md#4-测试策略) 与 [AGENTS.md § CI 对齐](../../AGENTS.md#7-ci-对齐) |
| 打包发布 | 见 [README.md § 打包（Nuitka）](../../README.md#打包nuitka) |
| 服务端接入 | 见 [AGENTS.md § Spring Boot 服务端接入](../../AGENTS.md#5-spring-boot-服务端接入已接入) |

---

## 如何添加新指南

1. 在此目录新建 Markdown 文件，命名为 `topic.md`。
2. 只写操作步骤、命令、验证方式；架构背景指向 `docs/ARCHITECTURE.md`。
3. 需要列配置、API、Bridge Slot 时，指向 `docs/reference/`，不要复制完整表格。
4. 将新指南加入本索引表。

---

## 指南模板

```markdown
# [任务名称]

**目的**: [简要说明这个任务解决什么问题]

## 前置条件

- [环境要求]
- [必要工具]

## 步骤

1. [第一步]
2. [第二步]

## 验证

[如何确认任务完成成功]

## 相关链接

- @see docs/ARCHITECTURE.md
- @see docs/reference/
```

---

**维护者**: typetype 开发团队
