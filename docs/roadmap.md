# TypeType 功能路线图

> 最后更新：2026-04-17
>
> 本文档用于说明 **当前已完成能力** 与 **后续规划方向**。
>
> 注意：这是路线图，不是当前架构事实来源；涉及层次划分、命名、依赖方向时，请以 [ARCHITECTURE.md](./ARCHITECTURE.md) 和源码为准。

---

## 当前已完成能力

### 1. 打字训练主流程

- `TypingPage.qml` 作为主训练页面
- 支持“载文 / 剪贴板载文 / 重打”
- 支持实时展示：
  - 速度
  - 击键
  - 码长
  - 错误数
  - 用时
- 打字结束后弹出成绩摘要
- 历史记录可在当前会话中展示

### 2. 文本加载链路闭口完成

当前实际链路：

```text
Bridge -> TextAdapter -> LoadTextUseCase -> TextSourceGateway
```

已经明确的职责划分：

- `TextAdapter`：Qt 信号、线程协调、错误回传、UI 来源展示
- `LoadTextUseCase`：文本加载编排入口
- `TextSourceGateway`：配置查询 + 本地/远程来源路由
- `QtLocalTextLoader` / `RemoteTextProvider`：具体实现

### 3. 字符级统计与薄弱字

已完成：

- `CharStat` 实体
- `CharStatsService`
- `SqliteCharStatsRepository`
- `WeakCharsPage.qml`
- `WeakCharsQueryWorker`

当前可用能力：

- 跨会话持久化字符统计
- 查询薄弱字 Top N
- 展示错误率、平均耗时、输入次数等信息

### 4. 认证基础能力

已完成：

- `AuthService`
- `ApiClientAuthProvider`
- token 校验与刷新
- 登录状态初始化

### 5. 基础平台适配与工程化

已完成：

- Linux / Windows 基础运行支持
- Wayland 特殊处理与降级
- GitHub Actions：
  - `ci.yml`
  - `multi-platform-tests.yml`
  - `build-release.yml`
- Nuitka 打包脚本

### 6. 排行榜（基础实现）

已完成：

- `LeaderboardProvider` Port 协议
- `LeaderboardGateway` + `LeaderboardAdapter` + `LeaderboardWorker`
- `TextLeaderboardPage.qml`（Master-Detail 文本排行浏览）
- `DailyLeaderboard.qml`（日榜页面）
- `typing/LeaderboardPanel.qml`（TypingPage 右侧面板）
- 成绩提交后自动刷新排行榜

已知未修复 Bug：见 `docs/unfixed-bugs-2026-04-15.md`

### 7. 成绩提交与文本上传

已完成：

- `ApiClientScoreSubmitter`（服务端文本可提交成绩）
- `TextUploader`（本地文本上传到云端）
- `UploadTextAdapter` + `UploadTextPage.qml`
- 上传结果 text_id 通过信号传递到 TypingPage

---

## 当前代码中的核心对象

### QML / Presentation

- `Bridge`
- `TypingAdapter`
- `TextAdapter`
- `AuthAdapter`
- `CharStatsAdapter`
- `LeaderboardAdapter`
- `UploadTextAdapter`

### Application

- `LoadTextUseCase`
- `TextSourceGateway`
- `ScoreGateway`
- `LeaderboardGateway`
- `GlobalExceptionHandler`

### Workers

- `BaseWorker`
- `TextLoadWorker`
- `CatalogWorker`
- `LeaderboardWorker`
- `TextListWorker`
- `WeakCharsQueryWorker`

### Domain

- `TypingService`
- `CharStatsService`
- `AuthService`
- `SessionStat`
- `CharStat`

### Integration / Infrastructure

- `RemoteTextProvider`
- `QtLocalTextLoader`
- `SqliteCharStatsRepository`
- `ApiClient`
- `ApiClientAuthProvider`
- `ApiClientScoreSubmitter`
- `LeaderboardFetcher`
- `TextUploader`
- `QtAsyncExecutor`

---

## 近期可继续推进的方向

### A. 薄弱字驱动的推荐练习

目标：基于 `CharStatsService.get_weakest_chars()` 自动生成更有针对性的练习材料。

建议落点：

- 业务策略：`domain/services/` 或新增 UseCase
- 载文接入：复用 `LoadTextUseCase` / `TextSourceGateway` 边界
- UI 展示：新增页面或在 `TypingPage` 扩展入口

### B. 排行榜闭环完善

基础实现已完成（见上方"已完成功能 #6"），但仍有未修复 Bug：
- ToolLine 按钮显示异常
- TextLeaderboardPage ComboBox 为空
- 排行榜日期列不显示

详见 `docs/unfixed-bugs-2026-04-15.md`。

### C. 远端同步字符统计

目标：把本地 `CharStat` 聚合数据同步到服务端，实现多设备共享。

潜在落点：

- 新增同步 Port
- Integration 实现远端同步仓储
- Domain 层保留聚合逻辑

### D. AI Typing Coach

详见 [AI_AGENT_PLAN.md](./AI_AGENT_PLAN.md)。

目标方向：

- 基于薄弱字生成个性化练习文本
- 对生成结果做质量评估
- 形成“查询 -> 生成 -> 评估 -> 决策”的闭环

### E. Spring Boot 服务端接入

详见 [SPRING_BOOT.md](./SPRING_BOOT.md)。

目标方向：

- 文本服务自托管
- 排行榜与用户数据持久化
- 认证、成绩、统计后端化

---

## 建议的优先级

|| 优先级 | 方向 | 原因 |
||--------|------|------|
|| 高 | 推荐练习 | 直接复用现有 CharStats 能力，改动可控 |
|| 高 | 排行榜 Bug 修复 | 基础已实现，修复 3 个未解决问题即可闭环 |
|| 中 | 远端同步字符统计 | 架构价值高，但涉及服务端协作 |
|| 中 | Spring Boot 接入 | 价值高，但跨端改动更大 |
|| 中 | AI Typing Coach | 展示性强，但属于扩展型能力 |
|| 低 | 更细粒度学习分析 | 需要更多数据模型与 UI 设计 |

---

## 里程碑建议

### Milestone 1：练习体验增强

- 推荐练习入口
- 基于薄弱字的文本选择/生成
- 训练完成后回流统计

### Milestone 2：排行榜与个人数据闭环（部分完成）

- ✅ 成绩提交通路（ApiClientScoreSubmitter）
- ✅ 排行榜基础实现（TextLeaderboardPage + LeaderboardPanel）
- 🔧 排行榜 Bug 修复（见 unfixed-bugs-2026-04-15.md）
- 个人中心统计完善

### Milestone 3：云同步

- 字符统计远端同步
- 多设备数据一致性

### Milestone 4：AI 教练能力

- 个性化载文
- 自动评估与推荐
- 训练反馈闭环

---

## 这份路线图刻意不做的事

- 不把历史命名（如旧网关名、旧 worker 名、旧目录名）继续当作当前事实
- 不替代 `ARCHITECTURE.md` 解释分层规则
- 不描述尚未落地的“应该如何实现”为“已经如此实现”

---

## 版本历史

|| 日期 | 变更 |
||------|------|
|| 2026-04-17 | 更新核心对象清单（补 LeaderboardAdapter/Gateway/Worker、UploadTextAdapter 等）；排行榜与成绩提交移至已完成功能；优先级表更新 |
|| 2026-04-06 | 基于当前代码重写路线图，移除历史命名与过时分层描述 |
