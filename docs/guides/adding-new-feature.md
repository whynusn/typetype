<!-- 状态: active | 最后验证: 2026-06-04 -->
# 如何添加新功能（Guide）

> 目标：遵循项目架构规范，在正确的位置添加功能。

---

## 决策树

先看你想加什么，决定改哪里：

```
┌─────────────────────────────────┐
│  你想加什么？                    │
└────────────┬────────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
  新文本来源        新统计规则
    │                 │
    ▼                 ▼
  integration/    domain/services/
  ports/          + entity/
  text_source_    + 测试
  gateway.py
    │
    ▼
  新 QML 页面？── 是 ──→ src/qml/pages/ + Bridge + Adapter
    │
    否
    │
    ▼
  新后台任务？── 是 ──→ workers/ + Bridge Slot
    │
    否
    │
    ▼
  配置变更？── 是 ──→ RuntimeConfig + config.example.json
```

## 通用流程

1. **读 ARCHITECTURE.md** — 确认你理解当前分层
2. **写测试** — TDD，先写失败测试
3. **实现功能** — 按决策树定位文件
4. **跑测试** — `uv run pytest -v`
5. **检查代码** — `uv run ruff check . && uv run ruff format --check .`
6. **更新文档** — 按 [AGENTS.md § 文档维护指南](../../AGENTS.md#-文档维护指南)
7. **提交** — 代码和文档更新在同一提交

## 相关参考

- 分层和依赖规则：[ARCHITECTURE.md § 分层架构](../ARCHITECTURE.md#分层架构)
- 代码规范和实践陷阱：[AGENTS.md § 代码风格](../../AGENTS.md#3-代码风格)
- 配置、Bridge、QML、API 速查：[docs/reference/](../reference/)
