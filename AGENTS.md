# typetype 项目开发指南
<!-- 状态: active | 最后验证: 2026-06-04 -->

## 📍 文档导航卡（你在这里）

本文档面向 **AI 开发者**，记录编码规范和已知陷阱。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 开发约束、编码规范、已知陷阱 | [README.md](./README.md) — 快速入门<br>[ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 架构权威 | [代码风格](#3-代码风格)<br>[已知陷阱](#8-已知陷阱) |

---

## 🧭 AI 阅读顺序

1. **本文档 §3 代码风格 + §8 已知陷阱** — 编码约束和常见坑位
2. **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — 架构分层、数据流、依赖规则
3. **[docs/reference/README.md](./docs/reference/README.md)** — 配置/QML/API 速查
4. **本文档 §4-7** — 测试策略、服务端接入、平台权限、CI
5. **[docs/history/](./docs/history/)** — 历史功能设计文档（已完成，仅作背景参考）

> 已熟悉项目后，日常开发只需查阅 **§3 代码风格 + §8 已知陷阱** 即可。

---

## 📚 文档维护指南

### 文档职责速查

| 文档 | 角色 | 什么时候更新 |
| :--- | :--- | :--- |
| `ARCHITECTURE.md` | 唯一事实来源（"宪法"） | 新增/删除文件、架构变更、新架构陷阱 |
| **本文档** | AI 开发约束与陷阱集 | 新坑位、编码规范变化、验证要求更新 |
| `docs/reference/*` | 速查表 | 配置字段、Bridge Slot、API 端点变化 |
| `docs/decisions/*` | 架构决策记录（ADR） | 做出重大架构决策 |
| `docs/history/*` | 历史设计文档归档（冻结） | 完成重大功能、修复复杂 bug |
| `CHANGELOG.md` | 发布历史 | 版本发布或用户可见变更 |

### 权威矩阵

> 摘要；完整定义（含跨维度冲突处理）见 [docs/meta/README.md](./docs/meta/README.md#权威矩阵冲突解决)。<!-- @summary from:docs/meta/README.md -->

**事实可靠性链**：源码 > ARCHITECTURE.md > reference/* > decisions/* > AGENTS.md > guides/* > history/*

**操作优先级链**：AGENTS.md > guides/* > ARCHITECTURE.md > decisions/* > reference/* > history/*

### 修改代码后的文档更新流程

```
改完代码
  ↓
判断变更类型（见上表；逐项映射见 docs/meta/README.md § 同步规则）
  ↓
更新对应文档
  ↓
验证：运行 docs/meta/README.md § 验证清单
```

### 提交前验证清单

- [ ] `ARCHITECTURE.md` 目录结构与 `src/backend/` 实际文件一致
- [ ] `docs/reference/` 中的表格与代码一致
- [ ] `ARCHITECTURE.md` 陷阱覆盖最新发现
- [ ] 所有内部链接无断链
- [ ] 本文档陷阱描述准确
- [ ] `CHANGELOG.md` 已更新（若涉及用户可见变更）

---

## 1. 开发环境与命令

> 详细见 [ARCHITECTURE.md § 快速开始](./docs/ARCHITECTURE.md#快速开始)。

### 字体裁剪

| 字体 | 原始大小 | 裁剪后大小 | 减少 |
|:--- |:--- |:--- |:--- |
| HarmonyOS Sans SC Regular | 8.2 MB | 504 KB | ~94% |
| LXGW WenKai Regular | 25.4 MB | 880 KB | ~97% |

打包时使用 `*-subset.ttf` 而非原始字体。

---

## 💬 用户快捷操作指令

| 用户说 | AI 执行 |
|:--- |:--- |
| **"项目概览"** | 阅读 README 摘要 + ARCHITECTURE 一句话理解，汇总输出 |
| **"同步文档"** | 按"代码变更→文档更新映射"逐项检查更新 |
| **"检查文档"** | 运行 `scripts/verify-framework.sh`，汇总结果 |
| **"记录决策"** | 在 `docs/decisions/` 创建 ADR |
| **"更新 CHANGELOG"** | 检查 git 提交，追加版本条目 |

---

## 2. 当前架构速查

> 完整架构见 [ARCHITECTURE.md](./docs/ARCHITECTURE.md)。

### 薄弱字排序

`CharStatsRepository.get_chars_by_sort(sort_mode, weights, n)`：

| sort_mode | 说明 |
|:--- |:--- |
| `error_rate` | 按错误率排序（默认） |
| `error_count` | 按错误次数排序 |
| `weighted` | 加权排序，`weights = {"error_rate": float, "total_count": float, "error_count": float}` |

### 架构约束

**绑定规则**：Presentation 只能依赖 Application 层，禁止依赖 Domain 层。

**决策规则**：
- 有编排逻辑 → 必须走 UseCase
- 纯转发无分支 → Adapter 可直连 Gateway
- 异常转换 → `GlobalExceptionHandler` 统一处理

**Bridge 职责（薄适配层）**：
- 属性代理：透传各 Adapter 只读属性到 QML
- 信号转发：Adapter 信号转发到 QML
- Slot 入口：QML 请求转发到对应 Adapter
- **禁止直接访问 `SessionContext`**，所有状态访问必须通过 `TypingAdapter` 代理

---

## 3. 代码风格

### Python

- 导入顺序：标准库 → 第三方 → 本地
- 命名：类 `PascalCase`，函数/变量 `snake_case`
- 函数参数与返回值必须有类型提示
- 外部 I/O（网络/系统）必须有异常处理

### Qt/QML

- 使用 `Property + notify signal` 做响应式更新
- UI 不执行耗时任务，走 `workers`
- RinUI `ContextMenu` 的 `height` 动画用 `Behavior on height`，不用 `enter` transition
- `FluentPage` 不使用 `layer.effect: OpacityMask`
- **FluentPage 内容区子项必须用 `Layout.*` 而非 `anchors`**
- **QQC 必须限定导入 `as QQC`**（避免与 RinUI 同名组件冲突）
- 所有载文入口页（CustomLoadTextPage、LocalArticlesPage、TrainerPage、JisuBeiPage）应保持一致的 UI 模式

---

## 4. 测试策略

- 优先覆盖用例层与核心逻辑，不依赖真实 UI
- 对网络错误、超时、解析异常必须有测试
- 新增文本来源时补充：`LoadTextUseCase` 测试 + `GlobalExceptionHandler` 测试 + service/integration 测试

---

## 5. Spring Boot 服务端接入

已通过 `RemoteTextProvider`、`ApiClientScoreSubmitter`、`LeaderboardFetcher` 等接入 [typetype-server](https://github.com/whynusn/typetype-server)。

### 接入原则

- 用例层只依赖 Port 协议，不直接依赖 HTTP 细节
- Spring Boot 后端作为 integration 层实现注入

### 新增服务端能力扩展路径

1. `ports/` 定义新 Port 协议
2. `integration/` 实现对应 adapter
3. `main.py` 装配层注入
4. 配置项通过 `RuntimeConfig` 管理

> 当前接口列表见 [docs/reference/api-endpoints.md](./docs/reference/api-endpoints.md)。

---

## 6. 平台与权限

- Linux Wayland 全局键盘监听通常需要 `input` 组权限
- 不满足权限时优雅降级，不影响基础打字流程

---

## 7. CI 对齐

| 流程 | 内容 |
|:--- |:--- |
| `ci.yml` | ruff check / format check |
| `multi-platform-tests.yml` | Linux/Windows pytest |
| `build-release.yml` | Linux/Windows Nuitka 打包与 release |

本地验证：
```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

---

## 8. 已知陷阱（编码实践类）

> **分类说明**：架构设计类陷阱见 [ARCHITECTURE.md § 已知陷阱](./docs/ARCHITECTURE.md#已知陷阱)。新增陷阱时：编码实践类写在这里，架构设计类写在 ARCHITECTURE.md。

### ⚠️ TypingService.clear() 不要清零 char_count 和 wrong_char_count

**问题**：在 `clear()` 中清零 `char_count` 和 `wrong_char_count` 会导致删除时出现负数位置错误。

**原因**：QML `onTextChanged` 是异步的。`clear()` 中提前清零时，未完成的 `onTextChanged` 事件会以 `char_count=0` 计算出负数 `beginPos`。

**正确做法**：在 `set_total_chars()` 中清零，而非 `clear()`：

```python
def clear(self) -> None:
    self._state.session_stat.time = 0.0
    self._state.session_stat.key_stroke_count = 0
    # ❌ 不要清零 char_count / wrong_char_count
    self._state.session_stat.date = ""
    self._state.last_commit_time_ms = 0.0

def set_total_chars(self, total: int) -> None:
    self._state.total_chars = total
    self._state.session_stat.char_count = 0      # ✅ 这里清零
    self._state.session_stat.wrong_char_count = 0  # ✅ 这里清零
```

**历史**：2026-03-21 架构重构中首次出现。

### ⚠️ handle_committed_text 删除字符时的逻辑顺序

**正确顺序**：先处理 `s` → 更新 `char_count` → 最后清除被删除位置。

先更新 `char_count` 再处理 `s` 会导致使用更新后的值计算错误位置。

### ⚠️ 单实例页面切换时必须重置 appBridge 瞬态状态

**问题**：NavigationView 单实例模式下，页面切换后 `appBridge` 的瞬态状态（如 `textId`）仍保留上一次的值。

**修复**：在 `onActiveChanged` 中重置：

```qml
onActiveChanged: {
    if (active && appBridge) {
        appBridge.setTextTitle(appBridge.defaultTextTitle);
        appBridge.setTextId(0);  // 重置，强制重新载文
    }
}
```

### ⚠️ 领域模型不应承载 UI 路由概念

`SessionStat` 不应包含 `text_source_key`。来源标识是 UI 路由概念，不应污染领域层。

**历史**：2026-04-13 重构中删除。

### ⚠️ TextAdapter 所有文本加载必须走 Worker

**问题**：本地文本加载在主线程同步执行导致 UI 阻塞（隐含同步 HTTP 回查服务端 ID）。

**正确做法**：所有加载统一走 Worker。两阶段异步：Worker 只读文件 → daemon thread 异步回查。

**历史**：2026-04-16 发现，2026-04-19 拆分为两阶段。

### ⚠️ RinUI ContextMenu height 不能用 enter transition 动画

首次打开时 `ListView` 未完成布局，`implicitHeight` 为 0，导致动画到 ~6px 后缩回。

**正确做法**：`Behavior on height` + `enter` 只动画 opacity。

### ⚠️ RinUI ComboBox onActivated 不触发

使用 `textRole`/`valueRole` 时 `onActivated` 不触发。改用 `onCurrentIndexChanged` + 去重守卫。

### ⚠️ 清空 UpperPane 文本前必须先重置光标位置

分片载文模式下，清空前调用 `upperPane.setCursorAndScroll(0, false)`，防止 `QTextCursor::setPosition` 越界警告。

### ⚠️ 分片达标次数在片段切换时必须归零

进入片段时从 0 开始，片段内重打累加，离开时归零。同一片段重打时保留达标次数。

---

## 文档编写规范

- **事实文档**（ARCHITECTURE.md）：先结论后解释。代码块标注语言。
- **Agent 规则**（本文档）：简洁直接。陷阱包含：问题、原因、正确做法、历史记录。
- **速查表**（docs/reference/*）：纯表格，H1 + `>` 摘要行 + 表格主体。不写段落。≤ 200 行。
- **操作手册**（docs/guides/*）：只写步骤、命令、验证方式。架构背景指向 ARCHITECTURE.md。
- **历史归档**（docs/history/*）：完整记录背景、决策、实现、验证。不修改、不删除。
