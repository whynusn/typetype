# 开源文库 UX 重设计与 OTT Repo 标准对齐（v1.2 提案）

- **日期**: 2026-08-15
- **状态**: 提案待评审
- **范围**:
  - typetype 客户端：开源文库（载文中心 repos tab）的状态模型、刷新语义、组件 UX、标准字段消费
  - open-typing-texts：OTT Repo v1.2 增量提案（display metadata / refresh policy / derived authority / extension 策略 / directory 客户端行为 / Core EntrySummary 小修）
- **关联**: ADR-010（联邦订阅）、ADR-013（三仓收敛）、`docs/designs/dynamic-source-snapshot-freshness.md`、`docs/designs/ott-source-ecosystem-analysis.md`、open-typing-texts `docs/repo-manifest-spec.md` / `OTT_SPEC.md` / `schemas/*`

---

## 1. 背景与问题总览

### 1.1 本次触发问题的定性与根因

| 现象 | 定性 | 根因 |
|:---|:---|:---|
| 刷新 zenquotes 报 `ScriptSandbox 退出码 1: httpx.ConnectError` | 上游脚本源网络/DNS 失败，非客户端崩溃 | `ott-script` 在沙箱子进程内请求 `zenquotes.io`，本机 DNS 返回空列表；客户端已正确计入 `last_refresh_failed`，但 UI 反馈方式和范围错误 |
| 刷新「经典中文短句」后未变化的内容仍显示「刚刚」 | 语义 bug | `SnapshotCatalogService.refresh_source()` 对 force 手动刷新无条件 `save(captured_at=now)`；指纹跳过只存在于非 force 的 `refresh_and_list_all` 路径 |
| 单源刷新失败后整个开源文库列表被错误页替换 | UX bug | `RegistryAdapter._on_entries_refreshed()` 在源级失败时也发射全局 `entriesLoadFailed`，`TextLoadHubPage` 无条件写入 `reposEntriesError`，`RepoEntriesPanel` 用它盖住列表 |
| 组头类型看起来都一样 | UX 缺失 | UI 不渲染 L0/L1/L2/L3 能力层级；`ott-script` 被用户误认为 `ott-rule` |

### 1.2 typetype 客户端现状问题清单

| # | 位置 | 问题 | 优先级 |
|:--|:--|:--|:--|
| C1 | `snapshot_catalog_service.refresh_source` | force 刷新不比对内容指纹，静态源内容未变仍更新 `captured_at` | P0 |
| C2 | `registry_adapter._on_entries_refreshed` + `TextLoadHubPage` | 源级失败走全局错误态，盖住整个列表 | P0 |
| C3 | `RepoEntriesPanel.rebuild/rebuiltSourceFilter` | 筛选比较 `source_label`，而组名使用 `_source_label`，instance 源筛选失效 | P0 |
| C4 | `RegistryAdapter.refreshing_authority` | 单值标记并发刷新会互相覆盖，动画在源之间迁移 | P0 |
| C5 | `SnapshotCatalogService._last_refresh_*` | 成功/失败统计仅内存，重启后源健康状态丢失 | P1 |
| C6 | `RepoEntriesPanel` | 不展示来源类型、信任状态、调度频率、上次检查/失败状态 | P1 |
| C7 | `RepoConfigDialog` | 不展示 `description/maintainer/license/updated_at/incompatible_reason/unsupported_sources` | P1 |
| C8 | `refresh_policy.infer_policy` | 未消费 OTT Repo `rule.schedule`，所有 rule 一律 `on_demand` | P1 |
| C9 | `bridge.py` | `setSourceRefreshOverride/getSourceRefreshOverrides` 已存在但 QML 无入口 | P1 |
| C10 | `ott_repo_manifest._normalize_source` | `default_enabled/tags/schedule` 对 rule/script/bridge 未完整归一化 | P1 |
| C11 | `RepoEntriesPanel` | 随机源保留 5 条历史平铺，无「最新 + 历史」结构 | P2 |
| C12 | `ott_federation_provider` | `directory/repository-ref` 未被消费，添加订阅流程不支持目录 | P2 |
| C13 | `_BridgeClient._normalize_bridge_response` | 缺省 entry_id 生成 `bridge:<hex>`，违反 Core `entry_id` pattern `^[A-Za-z0-9_]+$` | 标准 P1 |
| C14 | `_script_authority` | 客户端使用 `script:{sha256(url)[:12]}`，与 open-typing-texts 规范文字「authority = script」不一致 | 标准 P1（需上游决策） |
| C15 | manifest 归一化 | `revocations/expires_at/snapshot_hash` 为 typetype 私有 TUF-lite 扩展，上游 schema 无定义 | 标准 P1 |
| C16 | `RepoEntriesPanel` 卡片 | freshness 只有「最新/可刷新/随机」，无法表达「上次检查失败，显示缓存」 | P1 |
| C17 | 列表/筛选 | 搜索不覆盖 tags/category；筛选结果为空的原因表达弱 | P2 |
| C18 | 添加订阅弹窗 | 只有 URL 输入，无目录浏览/仓库摘要预览 | P2 |

### 1.3 open-typing-texts 标准侧现状问题清单

| # | 位置 | 问题 | 建议 |
|:--|:--|:--|:--|
| S1 | `repo-manifest-spec.md §ott-script` | script authority 写为单一 `script`，多脚本会 authority/entry_id 冲突 | v1.2 改为 URL 指纹命名空间（与 typetype 现有实现一致，进度键同步） |
| S2 | `repo-manifest-spec.md` / schema | `schedule` 只存在于 `ott-rule`，且只有 `manual/hourly/daily`；adapter 参考实现还支持 `weekly`，客户端策略层支持任意 interval | v1.2 提升为**所有 source 类型公共的 `refresh` 策略**，统一模式与 `cache_ttl_seconds` 语义 |
| S3 | schema source 公共字段 | `default_enabled` 在 schema 里 rule/bridge/script 都有，但 prose 只写 instance；`label` 全部可选，fallback 不统一 | v1.2 统一公共字段并定义 fallback 顺序 |
| S4 | schema | 源级缺少 `description/rights_summary/homepage`，UI 没有可展示的说明与权利信息 | v1.2 增加可选 source display metadata |
| S5 | `OTT_SPEC.md` EntrySummary | 无 `category`；`fetched_at` 语义未定义；`char_count`/`charCount` 双拼并存 | v1.2 增加 `category` 可选、定义 `fetched_at`（服务端生成时间）与 `updated_at`（内容更新时间）、标注 `charCount` 为 legacy alias |
| S6 | `OTT_SPEC.md` EntrySummary | `entry_id` pattern 与客户端/桥接缺省派生 ID 存在冲突（`bridge:<hex>`） | v1.2 定义 derived entry_id 规则，客户端同步修正 |
| S7 | schema top-level | `additionalProperties: true` 但没有扩展字段政策；typetype 的 `max_entries`、`revocations`、`expires_at`、`snapshot_hash` 是事实扩展 | v1.2 定义 `x-` 命名空间与少量正式字段（`entry_limit`、TUF-lite 字段） |
| S8 | `repo-manifest-spec.md §Directories` | 只定义了目录不嵌套；没有定义客户端订阅流程、repository-ref 的信任/预览展示、目录签名语义 | v1.2 增加 Directory Client Behavior |
| S9 | `repo-manifest-spec.md §Trust` | 有 trust badge 要求，但没有 UI 呈现指南；L3 未验证跳过时客户端如何提示未规定 | v1.2 增加 Client Presentation Guidance（informative） |
| S10 | open-typing-texts 参考实现 | `ott_adapter` 的 script/entry 生成、validator fixtures、前端 source 卡片未覆盖上述新字段 | 标准落地后同步参考实现与 fixtures |

---

## 2. 目标与非目标

### 目标

1. 让开源文库每个源在 UI 上回答四件事：**是什么（类型/层级）、可不可信（trust）、多久更一次（refresh policy）、现在是否健康（last check/error）**。
2. 让刷新反馈严格按作用域隔离：**源级错误只影响该源组，列表级错误才盖全列表**。
3. 让 freshness 语义可解释：`captured_at`（内容变化）与 `last_checked_at`（检查成功）分离。
4. 把 OTT Repo v1.2 的增量提案写成可在 open-typing-texts 落地的最小标准变更集。
5. 所有改动可测试、可回滚，不破坏现有快照与进度键。

### 非目标

- 不重做 OTT Core v1 数据面协议（只做 additive 字段）。
- 不引入服务端/账号体系。
- 不在本提案内实现 `directory` 自动递归订阅（仅浏览 + 显式添加）。
- 不改变 L1 无图灵完备 / L3 沙箱安全边界。

---

## 3. 设计原则

1. **两个时间戳，两种含义**
   - `captured_at` = 该快照内容/归属元数据最近一次实际变化的时间。
   - `last_checked_at` = 该源最近一次网络物化检查成功的时间（即使内容没变）。
   - `last_error_at / last_error` = 最近一次失败时间与原因。
2. **源状态是持久化的一等公民**
   - `SourceStatusStore` 按 authority 存健康状态；快照条目仍是列表唯一事实源。
3. **错误按作用域收敛**
   - 源级刷新失败 → `sourceStatusChanged` + 组头内联状态；不发射全局 `entriesLoadFailed`。
   - 总刷新全部失败 → 全局错误页；部分失败 → 顶部/状态消息或组头徽章，不隐藏列表。
4. **标准优先**
   - OTT Repo 已定义字段必须先消费；typetype 扩展显式命名或以标准提案反哺上游。
5. **渐进披露**
   - 组头只放决策信息；描述/URL/license/权限放「源详情」，管理动作放「订阅管理」。
6. **刷新是状态机，不是布尔量**
   - `idle → refreshing → ok | failed | timeout`；成功/失败/超时三态都必须有终止态（沿用本轮已修的 worker 持有引用 + 序号守卫）。

---

## 4. 目标架构

### 4.1 数据模型

```text
EntrySnapshotStore（每 authority 目录）
  ├─ <entry_id>.json           # 现有快照：content/preview/...
  │    ├─ captured_at           # 内容实际变化时间（新语义）
  │    ├─ last_checked_at       # 新增：最近检查成功时间
  │    ├─ refresh_policy        # 现有
  │    └─ snap_fingerprint      # 现有
  └─ 可选：由 SourceStatusStore 另存 per-authority 状态文件

SourceStatusStore（新，per authority）
  ├─ last_checked_at / last_success_at
  ├─ last_error_at / last_error
  ├─ consecutive_failures
  ├─ refresh_policy（用户 override > manifest schedule > 推断）
  ├─ source_label / source_type / repo_id / repo_name / repo_url
  └─ trust_state / incompatible_reason / skipped_reason
```

> 状态文件建议放 `registry_cache/source_status/<authority-hash>.json`，与快照目录分离；读写复用 `EntrySnapshotStore` 的原子写模式。

### 4.2 刷新状态机与信号

```text
RegistryAdapter
  ├─ refreshingAuthorities: list[str]     # 替代单个 refreshing_authority 字符串
  ├─ sourceStatusChanged(authority, status: dict)
  ├─ entriesLoaded / entriesLoadFailed    # 只保留列表级语义
  └─ 手动刷新与 revalidate 双定时器       # 已实现，沿用

SnapshotCatalogService
  ├─ refresh_source(authority) -> RefreshOutcome
  │    ├─ federation.refresh_source
  │    ├─ 逐条 _snapshot_unchanged 判定
  │    │    ├─ 内容/归属未变 → 保留 captured_at，只更新 last_checked_at
  │    │    └─ 变化 → captured_at = now + last_checked_at = now
  │    ├─ 写 SourceStatusStore
  │    └─ prune + 返回统计
  └─ refresh_and_list_all(force)
       ├─ force 路径同样做 unchanged 判定（修正 C1）
       └─ 视图恒等于 list_cached()
```

### 4.3 源卡片信息架构（QML）

```text
┌ 源卡片（group header）────────────────────────────────────────┐
│ ▾ 一言（中文句子）            [L1] [已验证]      2 / 5 条       │
│   OTT Source Hub · 手动 · 刚检查过，内容已更新        [↻] [⋯]  │
└───────────────────────────────────────────────────────────────┘
│   entry card ...
│   entry card ...

┌ 源卡片─────────────────────────────────────────────────────────┐
│ ▸ 英文名言（zenquotes）        [L3] [已验证]      1 / 5 条       │
│   OTT Source Hub · 上次刷新失败（13:30）· 显示缓存    [↻] [⋯]  │
└─────────────────────────────────────────────────────────────────┘

┌ 源卡片─────────────────────────────────────────────────────────┐
│ ▾ 经典中文短句                 [L0] [未验证]      3 / 3 条 ▓▓▓  │
│   TypeType 内置文本源 · 静态 · 刚检查过，内容无变化    [↻] [⋯]  │
└─────────────────────────────────────────────────────────────────┘
```

- 第二行优先显示 `repo_name · 刷新策略 · 源状态`，URL 只在 tooltip 或详情弹窗展示。
- `[↻]` 对 static 源文案改为「检查更新」，tooltip 说明“检查是否有新内容，内容未变不刷新时间”。
- `[⋯]` 打开 `SourceInfoDialog`：label、类型层级、authority、repo、描述、tags、rights、license、维护者、调度频率、当前 override、最近检查/失败时间、原始 URL。

### 4.4 条目卡片 freshness 语义

| 显示 | 含义 | 数据 |
|:---|:---|:---|
| `最新` | 有 interval 策略且未到期，或 static 内容刚变化 | `captured_at + policy` |
| `可刷新` | interval 已到期 | `next_refresh_at <= now` |
| `随机` | on_demand 源，仅手动抽新 | `policy.mode == on_demand` |
| `缓存` | 最近一次刷新失败，正在显示旧快照 | `last_error` 存在且 `captured_at` 旧 |
| 副文本 | `内容 N 分钟前更新` 或 `刚检查，内容无变化` | `captured_at/last_checked_at` |

---

## 5. open-typing-texts v1.2 增量提案

> 该节是给上游的提案骨架；正式落地需在 open-typing-texts 仓开 ADR/PR，typetype 侧不自行修改规范权威。

### 5.1 公共 Source 字段（新增/统一）

```json
{
  "type": "ott-rule",
  "rule_id": "hitokoto",
  "label": "一言（中文句子）",
  "description": "每次返回一句中文短句",
  "rights_summary": "API provider terms apply",
  "homepage": "https://hitokoto.cn",
  "tags": ["quote", "chinese"],
  "default_enabled": true,
  "refresh": { "mode": "manual", "cache_ttl_seconds": 0 }
}
```

- `label`：v1.2 建议所有 source 类型 **required**；缺省 fallback 仅用于旧 manifest 迁移（instance→authority、rule→rule_id、script→URL host、bridge→bridge_kind）。
- `description/rights_summary/homepage`：可选，客户端详情页展示。
- `default_enabled`：四种 source 类型统一生效；客户端归一化必须保留。
- `refresh`：从 `ott-rule.schedule` 提升为公共字段（见 5.2）。

### 5.2 公共 `refresh` 策略（取代 rule 专属 `schedule`）

```json
"refresh": {
  "mode": "manual | hourly | daily | weekly",
  "cache_ttl_seconds": 0
}
```

映射：

| mode | 客户端 RefreshPolicy | 说明 |
|:---|:---|:---|
| `manual` | `on_demand` | 仅手动，不自动调度 |
| `hourly` | `interval(3600)` | 到期自动 revalidate |
| `daily` | `interval(86400)` | 到期自动 revalidate |
| `weekly` | `interval(604800)` | 与 adapter 参考实现对齐 |

- `cache_ttl_seconds` 语义：该源条目在客户端内存/文件缓存中的 TTL；`0` = 用客户端全局 `ott.cache_ttl_seconds`。
- 兼容：旧 `ott-rule.schedule` 保留 deprecated 读取，新 manifest 使用公共 `refresh`。
- 用户 per-source override 永远优先于 manifest 声明。

### 5.3 Derived Authority 命名空间

| Source | 现行规范 | v1.2 建议 |
|:---|:---|:---|
| instance | manifest `authority` 或 endpoint host | 不变 |
| rule | `rule:{repo_id}:{rule_id}` | 不变 |
| bridge | `bridge:{sha256(endpoint)[:12]}` | 不变 |
| script | `script`（单一） | **改为 `script:{sha256(payload_url)[:12]}`**，允许多脚本共存；进度键相应为 `ott:script:{sha25612}:{entry_id}@{revision_id}` |

理由：多个 repo 可分发多个脚本，单一 `script` authority 会把不同脚本的同名/同 hash entry 合并，违反“按 authority 命名空间隔离”原则。typetype 现有实现已经是 URL 指纹，规范文字应追上实现；进度键迁移见 §8。

### 5.4 Entry ID 与 Core 小修

- 明确 derived entry_id 规则：
  - `sha256(content)[:16]` 的十六进制直接使用（符合 pattern）；
  - **不得**加 `bridge:`/`script:` 等冒号前缀（当前 `bridge:<hex>` 违反 schema）。
  - 桥接器若缺 `entry_id`，客户端生成 `b<sha256(content)[:15]>` 或服务端发布显式 ID。
- `EntrySummary` 增加可选 `category`（string），客户端可筛选/展示。
- 定义 `updated_at`（内容更新时间）与 `fetched_at`（服务端抓取时间）区别；`charCount` 标记为 legacy alias，新发布内容统一 `char_count`。

### 5.5 扩展字段政策与 TUF-lite 标准化

- 顶层 `additionalProperties: true` 保留，但明确：**未在 schema 定义的字段 MUST 使用 `x-` 前缀**；客户端忽略未知字段。
- 把 typetype 已事实使用的字段正式化或改名：
  - `max_entries` → v1.2 正式字段 `entry_limit`（repo 级、可选、正整数；客户端继续读旧 `max_entries` 到 v1.3）。
  - `expires_at / snapshot_hash / revocations` → 进入 v1.2 schema（TUF-lite 小节），与 typetype `RepoManifestCache` 语义一致。
- `trust.required` 保持 reserved；目录签名沿用 repository 的 canonical bytes 规则。

### 5.6 Directory Client Behavior（informative → normative）

- 客户端识别 `type == "directory"` 后：拉取 manifest → 展示 `repository-ref` 列表（label/tags/url）→ 用户显式添加，不自动订阅。
- `repository-ref` 目标仍是普通 repository manifest；目录不得嵌套。
- 目录信任状态按 repository 同一 TOFU 规则处理；未验证目录仅影响目录自身展示，不阻止其中仓库被显式添加。
- 客户端对目录拉取失败应展示错误和重试，不阻塞本地已订阅源。

### 5.7 Client Presentation Guidance（新增 informative 节）

- 客户端 SHOULD 展示：source tier（L0-L3）、repo trust badge（verified/unverified/pending/failed）、refresh 状态（ok/failed/stale）与 incompatible reason。
- L3 因 `trust_state != verified` 跳过时 MUST 显示可操作的说明（“需信任该订阅源”），不得静默。
- 失败源的缓存快照 MUST 继续可读，并标注“显示缓存快照”。

---

## 6. typetype 落地计划

### Phase 0 — 语义与反馈修复（先做，低风险）

| 任务 | 文件 | 内容 | 测试 |
|:--|:--|:--|:--|
| T0.1 | `entry_snapshot_store.py` | `save(..., last_checked_at=None)`；旧快照无该字段视为缺省 | 单测：字段读写、旧文件兼容 |
| T0.2 | `snapshot_catalog_service.py` | `refresh_source` 逐条调 `_snapshot_unchanged`；未变化保留 `captured_at` 仅写 `last_checked_at`；force 与 revalidate 共用判定 | 单测：静态同内容刷新 `captured_at` 不变、`last_checked_at` 变；内容变化二者都变 |
| T0.3 | `registry_adapter.py` | 新增 `sourceStatusChanged(str, dict)`；源级成功/失败只发源状态；`refreshing_authority` 替换为 `refreshing_authorities: list[str]` | adapter 测试 + 真实 QThreadPool 回归 |
| T0.4 | `bridge.py` | 代理 `refreshingFederatedSources`（list）与 `sourceStatusChanged` | bridge/QML 引用测试 |
| T0.5 | `RepoEntriesPanel.qml` / `TextLoadHubPage.qml` | 源级错误不再写 `reposEntriesError`；组头显示失败 chip + 重试；筛选改用 `_source_label || source_label` | QML 静态断言测试 |
| T0.6 | `RepoEntriesPanel.qml` | 并发刷新动画按集合判定；static 源按钮 tooltip「检查更新」 | 同上 |

### Phase 1 — 源状态与标准字段消费

| 任务 | 文件 | 内容 | 测试 |
|:--|:--|:--|:--|
| T1.1 | `integration/source_status_store.py`（新） | per-authority 状态持久化：last_checked/success/error、consecutive_failures、policy、source/repo 元数据 | 单测：原子写、损坏文件容错 |
| T1.2 | `snapshot_catalog_service.py` | 刷新结果回写 `SourceStatusStore`；`list_cached` 输出附源状态（或 catalog 提供 `list_source_statuses`） | service 测试 |
| T1.3 | `ott_repo_manifest.py` | 归一化保留 rule/script/bridge 的 `default_enabled/tags/refresh/schedule/description/rights_summary/homepage` | manifest 测试 + 与 open-typing-texts fixtures 对齐 |
| T1.4 | `refresh_policy.py` / `snapshot_catalog_service._policy_for` | `manifest refresh` → RefreshPolicy；用户 override 优先级不变 | 单测：manual/hourly/daily/weekly 映射 |
| T1.5 | `RepoEntriesPanel.qml` | tier badge（L0-L3）、trust badge、refresh policy 文案、源状态 chip | QML 测试 |
| T1.6 | `SourceInfoDialog.qml`（新） / `RepoConfigDialog.qml` | 源详情（描述/tags/rights/license/maintainer/homepage/authority/URL）与调度覆盖下拉（接 `setSourceRefreshOverride`）；订阅管理展示 `incompatible_reason/unsupported_sources` | QML 引用测试 |
| T1.7 | `TextLoadHubPage.qml` | 总刷新部分失败显示非阻塞 statusMessage；全部失败才错误态 | 现有 backend/QML 测试扩展 |

### Phase 2 — 体验重构

| 任务 | 文件 | 内容 | 测试 |
|:--|:--|:--|:--|
| T2.1 | `RepoEntriesPanel.qml` | 源卡片重设计（信息架构见 §4.3）；URL/描述渐进披露 | 视觉走查 + QML 静态测试 |
| T2.2 | `RepoEntriesPanel.qml` | on_demand 源默认显示最新 1 条 + 「历史 N 条」展开；interval/static 维持现有 | QML 分组逻辑测试 |
| T2.3 | `AddRepoDialog` / federation | 识别 directory manifest，展示 repository-ref 列表供显式添加 | federation/manifest 测试 |
| T2.4 | `RepoEntriesPanel.qml` | 搜索覆盖 title/preview/source_label/category/tags；无匹配态说明更具体 | QML 测试 |
| T2.5 | `TextLoadHubPage.qml` | 后台 revalidate 完成时给出非打断提示（“已后台更新 N 个源”） | 后端信号测试 |

### 标准侧（open-typing-texts）落地任务

| 任务 | 位置 | 内容 |
|:--|:--|:--|
| S1 | `docs/repo-manifest-spec.md` | v1.2 变更：公共 source metadata、公共 `refresh`、derived authority、extension 政策、directory client behavior、presentation guidance |
| S2 | `schemas/ott-repo.schema.json` | 公共 `$defs/source_common`；`refresh`；`entry_limit`；TUF-lite 字段；`x-` 政策注释；label required 决策 |
| S3 | `schemas/ott-rule-v2.schema.json` | 移除/弃用 rule 内 `schedule`（改公共 `refresh`），保留兼容 fixture |
| S4 | `OTT_SPEC.md` | EntrySummary `category`、`updated_at/fetched_at` 语义、derived entry_id 规则、`charCount` legacy 说明 |
| S5 | `tests/fixtures/ott/...` | v1.2 fixtures：公共 refresh、entry_limit、directory、derived authority、非法 entry_id 拒绝 |
| S6 | `ott_adapter` 参考实现 | script 生成 authority/entry_id 按 v1.2；validator 校验公共字段；frontend source 卡片展示 tier/trust/refresh 状态（若本提案范围包含） |
| S7 | 上游 ADR/PR | 与 typetype 设计文档互链，标注 typetype 已消费/未消费状态 |

---

## 7. 兼容性与迁移

### 7.1 快照

- 旧快照无 `last_checked_at`：首次 revalidate 补写 `last_checked_at = captured_at`，不改 `captured_at`。
- `refresh_source` 首次对旧快照比较：`snap_fingerprint` 缺失视为“已变化”，补写指纹，但 **不再无条件更新 `captured_at`**；如归属元数据也相同，保留原 `captured_at`。
- 内容未变判断沿用 `_snapshot_unchanged` 的字段集（指纹 + `_repo_*` + `_source_label/_source_type`）。

### 7.2 进度键

- rule/instance/bridge 进度键不变。
- script authority 若采纳 v1.2 URL 指纹命名空间：typetype 现有进度键与快照目录 hash 不变（客户端已如此实现）；仅当旧版本曾按单一 `script` authority 落盘时需要一次性迁移。当前代码库无此旧格式，风险低。
- 若上游坚持单一 `script`，则本提案 S1 反向执行，且需要 authority 冲突解决与进度键迁移；**该决策阻塞 T1.5 的 script tier 展示细节，但不阻塞 Phase 0**。

### 7.3 配置

- `source_refresh_overrides` 结构不变；`RuntimeConfig` 无需 schema bump。
- `max_entries` 兼容读取：`entry_limit` 优先，`max_entries` 回退；两者都无则无上限。

---

## 8. 验收标准

1. 手动刷新内容未变的 static 源后：`captured_at` 不变、`last_checked_at` 更新、UI 显示“刚检查过，内容无变化”，不再出现“刚刚”虚刷。
2. 任意单源刷新失败：列表与其他源保持可交互；失败源组头出现失败 chip + 缓存提示 + 重试；不出现整页错误。
3. 并发刷新两个不同源：两个组头动画各自显示并各自结束。
4. manifest `refresh` 与用户 override 的优先级符合“用户 > manifest > 推断”；调度只作用于 interval 到期源。
5. 源组头展示 tier/trust/refresh/health 四要素；`SourceInfoDialog` 展示标准元数据。
6. open-typing-texts v1.2 schema 与 prose 一致，新 fixtures 全绿；typetype 全量 pytest/ruff 通过。
7. 全部失败的总刷新仍显示“刷新失败（网络不可达或源不可用），当前显示的是缓存快照”。

---

## 9. 待决策项

| # | 决策 | 推荐 |
|:--|:--|:--|
| D1 | script authority 采用规范单一 `script` 还是 URL 指纹 | 修订规范为 `script:{sha256(url)[:12]}`（多脚本隔离） |
| D2 | `max_entries` 正式字段名 | `entry_limit`，兼容旧名 |
| D3 | 公共 refresh 是否加入 `weekly` | 是，与参考实现对齐 |
| D4 | force 手动刷新在内容未变时是否更新 `captured_at` | 不更新；只更新 `last_checked_at` |
| D5 | 目录订阅是否自动 | 只浏览 + 显式添加 |
| D6 | 源详情弹窗与订阅管理弹窗合一还是分开 | 分开：SourceInfoDialog（只读+刷新策略）+ RepoConfigDialog（管理） |

---

## 10. 交付物

1. 本设计文档（typetype `docs/designs/open-library-ux-ott-repo-alignment.md`）。
2. typetype Phase 0-2 的实现 + 测试。
3. open-typing-texts v1.2 提案 PR 草稿（spec + schema + fixtures + 参考实现同步）。
4. 更新 `AGENTS.md` 已知陷阱与 `CHANGELOG.md`（实现阶段）。
