# 客户端与后端成绩指标契约对齐 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对齐 `typetype` 与 `typetype-server` 在成绩提交、排行榜返回和数据库持久化上的指标契约，消除“客户端指标已调整，但服务端接口/表结构仍停留在旧版本”的不一致。

**Architecture:** 以客户端当前 `SessionStat` 与指标定义文档为事实来源，先冻结一份新的成绩契约，再同步改造客户端提交层、服务端 DTO/Service/Mapper、Flyway 迁移、排行榜返回结构与相关文档。

**Tech Stack:** Python 3.12, PySide6/QML, Java Spring Boot, MyBatis, MySQL, Flyway

---

## 现状结论

### 1. 当前客户端的“事实指标集”已经不是旧接口那一套

- `src/backend/models/entity/session_stat.py` 定义了 `backspace_count`、`correction_count`、`keyAccuracy`、`effectiveSpeed` 等新旧混合指标，且 `keyAccuracy` 的算法已经落地。
- `docs/reference/typing-metrics.md` 已把 `退格数`、`回改数`、`键准`列为核心统计口径。
- `src/backend/models/dto/score_dto.py` 和 `src/backend/application/gateways/score_gateway.py` 已把 `回改 / 退格 / 键准 / 键数` 纳入本地展示与剪贴板输出。

### 2. 客户端提交层仍是“半新半旧”

- `src/backend/integration/api_client_score_submitter.py` 当前发送：
  `textId / speed / effectiveSpeed / keyStroke / codeLength / accuracyRate / keyAccuracy / charCount / wrongCharCount / duration`
- 这里已经多发了 `keyAccuracy`，但没有发送 `backspaceCount` 和 `correctionCount`。
- 同时接口名仍沿用旧语义：`accuracyRate`、`duration`，与客户端当前内部命名 `accuracy`、`time` 不完全一致。

### 3. 服务端从 DTO 到数据库仍停留在旧成绩模型

- `../typetype-server/src/main/java/com/typetype/score/dto/SubmitScoreDTO.java` 只接收旧字段：`effectiveSpeed / accuracyRate / charCount / wrongCharCount / duration`，没有 `keyAccuracy / backspaceCount / correctionCount`。
- `../typetype-server/src/main/java/com/typetype/score/entity/Score.java`、`ScoreVO.java`、`LeaderboardVO.java` 均没有新指标字段。
- `../typetype-server/src/main/java/com/typetype/score/mapper/ScoreMapper.java` 的插入 SQL 和排行榜查询 SQL 也只覆盖旧列。
- `../typetype-server/src/main/resources/db/migration/V1__create_tables.sql` 中 `t_score` 表缺少 `key_accuracy / backspace_count / correction_count` 列。

### 4. 排行榜消费端也还在吃旧返回结构

- `src/qml/pages/TextLeaderboardPage.qml` 与 `src/qml/pages/DailyLeaderboard.qml` 当前仍展示 `accuracyRate / wrongCharCount / duration`。
- 这意味着即便服务端完成新字段落库，客户端榜单页如果不改，也无法展示新指标体系。

---

## 推荐目标契约

建议把“服务端存储真值”切到客户端当前的原始统计口径，并把旧字段降为兼容字段或派生字段。

### 提交契约（推荐 V2）

必传字段：

- `textId`
- `speed`
- `keyStroke`
- `codeLength`
- `charCount`
- `wrongCharCount`
- `backspaceCount`
- `correctionCount`
- `keyAccuracy`
- `time`

兼容/派生字段处理建议：

- `accuracyRate`：可由 `charCount` 和 `wrongCharCount` 派生；短期可继续接受，长期不应作为唯一真值。
- `effectiveSpeed`：可由 `speed * accuracyRate` 派生；短期可继续返回，长期不建议作为必存列。
- `duration`：与客户端当前 `time` 语义相同；建议统一命名为 `time`，过渡期兼容 `duration`。

### 排行榜/历史返回契约（推荐）

至少返回：

- `speed`
- `keyStroke`
- `codeLength`
- `keyAccuracy`
- `charCount`
- `wrongCharCount`
- `backspaceCount`
- `correctionCount`
- `time`
- `createdAt`

如果为了平滑过渡，也可以在服务端保留兼容字段：

- `accuracyRate`
- `effectiveSpeed`
- `duration`

但这些字段应由服务端从真值字段推导，避免继续把旧列当主数据源。

---

## 需要修改的部分

### 客户端仓库 `typetype`

| 文件 | 变更 |
|------|------|
| `src/backend/integration/api_client_score_submitter.py` | 提交 payload 改为新契约；补发 `backspaceCount`、`correctionCount`；决定是否保留兼容旧字段 |
| `src/backend/models/entity/session_stat.py` | 作为契约真值来源保留；必要时补充注释说明哪些字段是原始值、哪些是派生值 |
| `src/backend/presentation/adapters/typing_adapter.py` | 若提交契约切到 `time`，确认异步提交拿到的是完整快照而不是清理后的值 |
| `src/qml/pages/TextLeaderboardPage.qml` | 榜单列切到新返回字段，或显式兼容新旧字段双读 |
| `src/qml/pages/DailyLeaderboard.qml` | 同上 |
| `docs/reference/typing-metrics.md` | 作为客户端指标真值文档，补充“对外 API 字段命名”章节 |
| `docs/reference/api-endpoints.md` | 更新客户端当前依赖的成绩接口字段说明 |
| `tests/` 下新增或更新提交器测试 | 锁定 payload 字段集合，避免再次出现“本地改了指标但接口没跟上” |

### 服务端仓库 `typetype-server`

| 文件 | 变更 |
|------|------|
| `src/main/java/com/typetype/score/dto/SubmitScoreDTO.java` | 接收新字段；设计兼容期校验规则 |
| `src/main/java/com/typetype/score/entity/Score.java` | 增加 `keyAccuracy`、`backspaceCount`、`correctionCount`，视方案决定是否保留 `effectiveSpeed`、`accuracyRate`、`duration` |
| `src/main/java/com/typetype/score/dto/ScoreVO.java` | 历史记录返回补充新字段 |
| `src/main/java/com/typetype/score/dto/LeaderboardVO.java` | 排行榜返回补充新字段 |
| `src/main/java/com/typetype/score/service/ScoreService.java` | 新旧字段映射、派生值计算、兼容逻辑集中在这里 |
| `src/main/java/com/typetype/score/mapper/ScoreMapper.java` | 插入 SQL、查询 SQL、排行榜 SQL 全部扩列 |
| `src/main/resources/db/migration/V7__align_score_metrics_contract.sql` | 新增迁移：补列、回填、索引评估 |
| `API_DOCS.md` | 更新提交/返回示例、字段表 |
| `docs/spring-boot-backend-design.md` | 更新服务端领域模型与 DDL |
| `docs/learning-guide-v2.md` | 清理旧示例，避免继续传播过期字段集合 |

---

## 实施步骤

### Task 1: 冻结成绩契约，先解决“叫什么、哪些是源字段”

**目标：** 先定一份 `ScoreSubmissionV2`，避免边改边争。

- [ ] 在客户端文档中明确：原始字段、派生字段、对外 API 字段名。
- [ ] 决策 `time` 与 `duration` 是否做重命名；如果要改名，确定过渡期长度。
- [ ] 决策 `effectiveSpeed`、`accuracyRate` 是“兼容返回字段”还是“继续持久化字段”。

**建议：**

- 原始字段入库，派生字段按需计算。
- 兼容期内服务端接受新旧字段，但数据库只保留一份真值。

### Task 2: 先改服务端入参和数据库，建立新真值存储

**Files:**
- `../typetype-server/src/main/java/com/typetype/score/dto/SubmitScoreDTO.java`
- `../typetype-server/src/main/java/com/typetype/score/entity/Score.java`
- `../typetype-server/src/main/java/com/typetype/score/service/ScoreService.java`
- `../typetype-server/src/main/java/com/typetype/score/mapper/ScoreMapper.java`
- `../typetype-server/src/main/resources/db/migration/V7__align_score_metrics_contract.sql`

- [ ] 为 `SubmitScoreDTO` 增加 `keyAccuracy`、`backspaceCount`、`correctionCount`、`time`，并定义兼容旧字段的校验规则。
- [ ] 新增 Flyway 迁移，为 `t_score` 增加缺失列。
- [ ] 在 `ScoreService` 中集中做新旧字段归一化：
  - 新接口传 `time` 时直接用 `time`
  - 旧客户端仍传 `duration` 时回填到 `time`
  - `accuracyRate`、`effectiveSpeed` 统一按当前真值重算或兜底
- [ ] 更新插入 SQL 与读取 SQL，保证新列真正持久化，不只是 DTO 表面扩字段。

### Task 3: 再改服务端返回结构，避免客户端榜单继续吃旧模型

**Files:**
- `../typetype-server/src/main/java/com/typetype/score/dto/ScoreVO.java`
- `../typetype-server/src/main/java/com/typetype/score/dto/LeaderboardVO.java`
- `../typetype-server/src/main/java/com/typetype/score/service/ScoreService.java`
- `../typetype-server/src/main/java/com/typetype/score/mapper/ScoreMapper.java`

- [ ] `ScoreVO`、`LeaderboardVO` 返回新指标字段。
- [ ] 兼容期内可同时返回旧字段，供未升级客户端继续工作。
- [ ] 排行榜排序规则保持 `speed DESC` 不变，避免本次契约对齐顺带改业务语义。

### Task 4: 回头改客户端提交器与榜单消费层

**Files:**
- `src/backend/integration/api_client_score_submitter.py`
- `src/qml/pages/TextLeaderboardPage.qml`
- `src/qml/pages/DailyLeaderboard.qml`

- [ ] 提交器补发 `backspaceCount`、`correctionCount`，并切换到新字段命名。
- [ ] 榜单页改成双读策略：
  - 优先读新字段 `keyAccuracy / time / correctionCount / backspaceCount`
  - 兼容读旧字段 `accuracyRate / duration`
- [ ] 客户端完成升级后，再视情况移除对旧字段的 UI 依赖。

### Task 5: 文档与测试一起补齐，防止再次漂移

**Files:**
- `docs/reference/typing-metrics.md`
- `docs/reference/api-endpoints.md`
- `../typetype-server/API_DOCS.md`
- `../typetype-server/docs/spring-boot-backend-design.md`
- `../typetype-server/docs/learning-guide-v2.md`

- [ ] 客户端新增提交 payload 测试，直接断言字段集合。
- [ ] 服务端新增 `SubmitScoreDTO` / `ScoreService` / `ScoreMapper` 测试，覆盖新旧字段兼容。
- [ ] 文档中的 JSON 示例、DDL、字段表全部更新到同一版本。

---

## 数据库迁移建议

推荐新增一条独立迁移，而不是修改旧的 `V1__create_tables.sql`。

### 建议迁移内容

- [ ] `ALTER TABLE t_score ADD COLUMN key_accuracy DECIMAL(5,2) NOT NULL DEFAULT 100.00`
- [ ] `ALTER TABLE t_score ADD COLUMN backspace_count INT NOT NULL DEFAULT 0`
- [ ] `ALTER TABLE t_score ADD COLUMN correction_count INT NOT NULL DEFAULT 0`
- [ ] 如果决定统一命名：
  - 新增 `time DECIMAL(10,2) NOT NULL DEFAULT 0`
  - 用 `duration` 回填 `time`
  - 兼容期结束后再评估是否删除 `duration`
- [ ] 如果决定不再把 `accuracy_rate` / `effective_speed` 当真值：
  - 保留旧列一段时间，避免旧查询立即失效
  - 等客户端和查询链路都切完，再做二次清理迁移

### 不建议的做法

- [ ] 不要直接改 `V1`，否则已部署环境无法重放。
- [ ] 不要在一次迁移里同时做“加列 + 删旧列 + 改排序规则”，回滚面太大。

---

## 验证清单

- [ ] 客户端提交一次成绩，请求体中包含新字段，且字段值与 `SessionStat` 一致。
- [ ] 服务端可同时接受新客户端请求和旧客户端请求。
- [ ] 新成绩写入数据库后，`t_score` 新列有值，不全是默认值。
- [ ] 排行榜接口返回的新字段能被客户端页面读取并正确展示。
- [ ] 历史成绩接口返回结构与文档一致。
- [ ] `API_DOCS.md`、客户端 `api-endpoints.md`、代码 DTO 字段表三者一致。

---

## 风险与注意事项

- **命名风险：** `time` 与 `duration`、`accuracy` 与 `accuracyRate`、`keyAccuracy` 是三套相近概念，必须在 Task 1 一次定清。
- **兼容风险：** 客户端榜单页当前仍吃旧字段，如果服务端只返回新字段，会直接造成显示缺项。
- **迁移风险：** `t_score` 是已有生产数据表时，删旧列必须晚于客户端和查询链路完成切换。
- **文档风险：** 当前两个仓库都已有过期字段示例；如果代码改了文档不改，下次还会重复同样的问题。

---

## 实施顺序摘要

1. 定契约，明确真值字段与兼容字段。
2. 先发服务端兼容版本：DTO + DB + Mapper + 返回结构。
3. 再发客户端版本：提交器 + 榜单消费。
4. 最后删兼容层：旧字段、旧文档、旧测试样例。
