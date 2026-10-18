# ADR-016: 源仓库与前端验收机制的架构收敛

<!-- 状态: accepted | 决策日期: 2026-10-18 | 最后验证: 2026-10-18 -->

> 实施状态（2026-10-18）：**阶段 A（验收能力补齐）进行中**——`wait.until` / `assert.timeout_ms` 轮询、`seed` 数据播种、`{{builtin_repo_url}}` 占位符、开源文库 objectName 锚点与 `app_open_library` 交互场景已落地；既有场景的"固定等待 + 一次性断言"已改为轮询断言。阶段 B（源仓库收敛）未开始。

> 与 [ADR-010](./010-decentralized-source-ecosystem.md)（源生态）、[ADR-011](./011-ott-source-ecosystem-hardening-plan.md)（加固）、[ADR-015](./015-ui-acceptance-harness.md)（验收 harness）配套。核心结论：**两套机制方向都对；验收机制补两项基础能力即可扩场景，源仓库的分层已经漂移、需要在场景保护下收敛，然后再加新功能。**

## 背景

2026-10-18 对两套机制做了一次架构评估（代码与 CHANGELOG 交叉核对）。

### 源仓库（OTT 联邦）

站得住的部分：L0–L3 分级 + 签名/TOFU 作为执行门槛；脚本子进程沙箱、正则 worker；"快照即视图 + 后台 revalidate"（stale-while-revalidate）；源健康状态与条目快照分存。

问题（按严重程度）：

1. **缓存叠了四层，新鲜度在多处判定**：`RepoManifestCache`（文件 TTL）→ 联邦内存 `_EntryCache`（TTL）→ `OttCachedFetcher`（instance 文件缓存）→ `EntrySnapshotStore`（指纹），外加 `RefreshPolicy` / `RefreshScheduler`。CHANGELOG 中「刷新按钮在 TTL 内无效」「后台刷新虚刷 freshness」「归属字段被指纹挡住不补写」同根。
2. **条目是无类型 dict + 注入的下划线字段**（`_authority/_source_label/_repo_id/_repo_name/_refresh_policy/_repo_trust_state…`），从 integration 一路流到 QML，schema 只存在于约定；QML 需要 `_source_label || source_label` 兜底。
3. **分组与状态机放错层**：`RepoEntriesPanel.qml`（1080 行）在 JS 中做分组/展开/历史折叠（「串组」「组头收不起来」出在这里）；`registry_adapter` 持有刷新集合、序号守卫、超时定时器——业务状态机住在 presentation 层。
4. **依赖方向不一致**：`SnapshotCatalogService`（application）直接 import 具体 integration 类、无 port；增删订阅/信任确认由 adapter 直写 `runtime_config`，删快照走 catalog——一个操作两条路径。
5. **并发靠约定**：catalog / 快照库无锁，依赖原子写 + adapter 序号守卫；历史上出过共享 httpx client 跨线程 double free。
6. **客户端跑在标准前面**：消费了上游 open-typing-texts 尚未合入的 v1.2 字段（refresh / tier / derived authority）。
7. `ott_federation_provider.py` 1314 行，四种 client 混在一起。

### 前端验收（ui-probe）

站得住的部分：冒烟 → 快照 → 真机 → 场景分层且子进程隔离；`ui_report.json` 作为 AI 唯一反馈接口；mock bridge 自动生成；检测器自检。

问题：

1. **没有"等到条件成立"**：`wait` 只是固定毫秒，`assert` 只判一次——慢机器间歇失败、快机器白等。
2. **缺数据播种层**：真机场景依赖环境里碰巧有的数据（默认订阅走网络 hub），开源文库因此只能测"切 tab 无噪声"。
3. **选择器偏脆**：55 处按可见文字定位；另有 41 处断言 bridge 属性（实为后端断言）。
4. **与 `bridge.py` 单文件强耦合**：AST 解析假设单个 Bridge 类；`tests/test_qml_pages.py` 另有一套正则解析——两个事实源。
5. offscreen ≠ 真实平台（macOS 原生标题栏段错误即例）。
6. P3 抽包为时尚早。

## 决策

### 阶段 A：验收能力补齐（先行，是阶段 B 的安全网）

1. **轮询语义**：`wait: {until: {find, expect}, timeout_ms}` 与 `assert.timeout_ms`。`no_new_messages` 不参与轮询（它消费消息窗口，反复求值会吞掉噪声导致假绿），其余条件成立或超时后只判一次。场景自检新增两条必然超时、一条必然成立的轮询步骤，并校验失败步确实等待过。
2. **数据播种**：真机场景可声明 `seed.config`（写成 `config.json`，自动补 `schema_version`）与 `seed.files`（`config:` / `data:` 语义根，经应用自身 `app_paths` 解析，禁止越界）。报告输出 `seeded` 文件列表。
3. **占位符**：`{{today}}`、`{{repo_root}}`、`{{builtin_repo_url}}`（内置离线仓库 file:// URL）。
4. **objectName 锚点**：关键交互控件（首先是开源文库：`repoGroupHeader` / `repoGroupRefresh` / `repoEntryRow` / `repoHistoryToggle` / `repoGroupFailed` / `repoAddButton` / `repoRefreshAll`）带 objectName 与 `groupKey` / `entryId` 等只读属性；文字选择器只用于断言文案。
5. **场景先钉住现有行为**：`app_open_library` 覆盖订阅 → 分组 → 展开/收起可逆 → 不串组 → 选中高亮 → 源级刷新后动画标记清空、条目不丢。后续补：信任 pending/确认/拒绝、刷新失败显示缓存、随机源历史展开、目录预览添加订阅。
6. 后续：bridge API 解析收敛为一个解析器并支持多注入对象；P2 只做 Linux xvfb nightly；P3 等出现第二个使用方。

### 阶段 B：源仓库收敛（在阶段 A 场景保护下，逐步、每步可回退）

1. **缓存收敛**：条目只留 `EntrySnapshotStore` 一层持久缓存；联邦层变为无状态抓取（移除 `_EntryCache` 与 per-client TTL）；"何时该抓"只由 catalog 按 `RefreshPolicy` 决定。manifest 缓存保留（控制面），但 TTL 判定统一。
2. **条目视图 DTO**：catalog 边界定义具名条目视图，归属信息（authority / repo / tier / trust）不再写进快照正文，由 catalog 在读取时组装。
3. **分组与状态机下沉**：分组 / 历史折叠在 Python 产出已分组 model；源级刷新状态机（并发集合、序号、超时）移入 catalog，adapter 只做线程与信号。
4. **订阅生命周期统一**：增删 / 启停 / 信任确认由 catalog（或独立订阅服务）编排，adapter 不直写 `runtime_config`；application 层经 port 依赖 integration。
5. **单写者**：同一 authority 的刷新串行化。
6. **拆分 `ott_federation_provider.py`**：四种 client 各自成模块。
7. **标准对齐**：把 2026-08-15 v1.2 提案推到 open-typing-texts；客户端对非标准字段保持向后兼容读取。

## 影响

- 阶段 A 只改验收工具、场景与 QML objectName（无行为变化）；既有场景的固定等待改为轮询后，总耗时下降、慢机器不再间歇失败。
- 阶段 B 每一步都必须让 `app_open_library` 与全量 pytest 保持绿；任何一步引入行为变化须先补场景。
- ADR-011 维持 `proposed`，直到 7.4（法务）与 1.4（极速杯许可）两项外部依赖有结论。
