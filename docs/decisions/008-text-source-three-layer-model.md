# ADR-008: 文本源三层模型（本地文件 / Registry 脚本 / 即时拉取）

<!-- 状态: accepted | 决策日期: 2026-07-05 | 最后验证: 2026-07-06 -->

> **2026-07-06 更新**：Registry 仓库已从"CI 生成内容"模式转型为"纯脚本工具"模式。
> Registry 仓库不再托管任何文本内容，也不运行 GitHub Actions 自动抓取。
> 仅提供抓取脚本模板，用户须在本地自行运行脚本生成文本。
>
> **2026-07-09 更新**：第 2 层进一步收敛为 OTT Core v1 + Distribution Profile。
> OTT 标准边界、大文本分段与 typetype 客户端演进见 [ADR-009](./009-ott-adapter-v2-and-large-text-distribution.md)。

## 背景

typetype 当前支持多种文本来源（本地文件、服务端 API、晴发文、CDN 注册表等），但来源扩展模型、晴发文的归属等问题长期缺乏统一决策。本文档综合对 Kimi「主仓库 + 独立适配仓库 + CI 脚本」提案的多轮分析结论，给出最终架构定性。

### 关键术语约定

为避免歧义，本 ADR 使用的术语含义如下：

| 术语 | 含义 |
|:---|:---|
| **文本源（Text Source）** | 用户打字练习的内容来源（如「前五百」「每日一文」「晴发文随机」）。在代码中由 `TextSourceEntry`（`src/backend/config/text_source_config.py`）表示，配置于 `config.json` 的 `text_sources` 字段。 |
| **Loader** | `TextSourceEntry.loader` 枚举，决定 `TextSourceGateway` 路由到哪个 Provider。取值：`LOCAL_FILE` / `REMOTE_API` / `REGISTRY`。 |
| **LeaderboardMode** | `TextSourceEntry.leaderboard_mode` 枚举，决定成绩提交时 `text_id` 如何解析。与 `Loader` 正交。 |
| **开源文库**（第 2 层） | 用户-facing 名称。由独立 git 仓库托管、提供纯脚本工具模板、客户端只读 JSON 拉取的文本源体系。 |
| **Registry** | 开源文库的内部实现标识符，用于代码命名（`RegistryTextProvider`、`RegistryConfig`、`registry.primary_url`）。 |
| **开源文库仓库** | 独立于 typetype 主仓库的第二个 git 仓库（如 `open-typing-texts`），提供抓取脚本模板（`scripts/`），用户本地运行生成 `content/*.json` 和 `registry_index.json`。**不提供任何现成文本内容，也不运行 CI 自动抓取。** |
| **即时拉取源** | 客户端通过 Worker 实时调用第三方/服务端 API 获取文本的来源（如晴发文 random、服务端 `/api/v1/texts/latest`）。 |
| **晴发文** | 第三方打字文本服务（代码标识符为 `wenlai`/`Wenlai`，`base_url` 默认 `https://qingfawen.fcxxz.com`，见 `src/backend/config/runtime_config.py` 的 `WenlaiConfig`），提供随机文本、相邻换段等接口，需要登录。 |

### 1.1 事实澄清（纠正前期认知偏差）

在评估「Kimi 提案（主仓库 + 独立适配仓库 + CI 脚本）」时，前期存在若干事实性误判，此处一并纠正：

| 命题 | 真假 | 证据 |
|:---|:---|:---|
| 当前架构「加来源必须改代码」 | ❌ 假 | `Loader + LeaderboardMode` 二维正交已配置驱动，本地来源只需 config.json 加一行（`text_source_config.py:42-51`、`runtime_config.py:374-386`）|
| 项目没有「独立仓库 + CI + 只读 JSON」能力 | ❌ 假 | `RegistryTextProvider` 已实现，注释明确「CI 生成 + 客户端只读不执行远程脚本」（`registry_text_provider.py:1-5`）|
| 晴发文应纳入 Registry/CI 体系 | ❌ **错** | 晴发文 `/api/texts/random`（`wenlai_provider.py:143`）+ `/api/texts/adjacent`（`wenlai_provider.py:180`）是即时交互 API，CI 化违 API 语义且违反账号模型（详见 §4.1）|
| Registry 的 `cache_ttl_seconds` 配置项生效 | ❌ 假 | 配置项存在（`runtime_config.py` 的 `RegistryConfig`），但 `RegistryTextProvider` 内**从未读取该字段**（死字段，`registry_text_provider.py` 全文无 ttl 逻辑），缓存目录只创建不读写 |

### 1.2 真正的缺口

1. **Registry 缓存层缺失**：`cache_dir` 只创建不读写，所有请求直打网络，弱网/离线即崩
2. **Registry catalog 未接 UI**：`RegistryTextProvider.get_catalog()` 全代码库无调用方；catalog worker 实际走的是 leaderboard API（`catalog_worker.py:16` → `leaderboard_gateway.py:8`），双路径分裂
3. **晴发文双轨制**：绕开 `TextSourceConfig`，独立 Port / Gateway / UseCase / Adapter / `SessionContext.setup_wenlai_session()`，与 Registry 体系并行
4. **静态仓库工件缺失**：`registry.primary_url` 指向的 Registry 仓库、CI workflow、`registry_index.json` schema 均未落地

### 1.3 关键认知

- **「每日一文 / 静态文集」** 适合 Registry + CI 化：增量、低频、可缓存、源站压力低
- **「晴发文 random」** 必须保持客户端 Worker 即时拉取：API 即时语义、账号私有、无全量接口
- **二者并存，不强行统一。**

### 1.4 CI 安全模型澄清

Kimi 原方案提到「沙箱执行适配脚本」，曾引起安全顾虑。本 ADR 明确：**抓取/解析脚本仅在 GitHub Actions CI 阶段运行，产物为纯 JSON，客户端只通过 HTTP GET 拉取 JSON，从不执行任何远程代码。** 此安全模型与现有 `RegistryTextProvider` 完全一致（`registry_text_provider.py:1-3` 注释），不存在 RCE 面。

---

## 选项

### A. 全部客户端即时拉取（不做 Registry/CI）

所有网络源都走 Worker 实时调用 API。

**优点**：单一加载路径，简单。
**缺点**：
- 无法支撑「每日一文」「静态文集」等天然适合缓存的场景
- 用户每次进入页面都打网络，弱网体验差
- 无「独立仓库 + 社区 PR」的扩展机制

### B. 全部 CI 化（Kimi 原方案的极端版本）

所有网络源都进 Registry 仓库，由 CI 抓取冻成 JSON。

**优点**：单一 CI 模型，社区贡献友好。
**缺点**：
- 晴发文 `/random` 是即时交互 API，CI 化破坏 random 语义（详见 §4.1）
- 晴发文无全量/分页接口，攒全库需 N 次 random 去重，撞 GHA 6h 限额且触发风控
- 违反晴发文账号模型（CI 持账号 = 账号共享）
- 对「实时源」强行套「缓存模型」，模型错配

### C. 三层模型（本 ADR 决策）

按「数据如何到达客户端」划分三类，每类有明确职责边界、扩展路径、网络/耗时特性，**不强行统一**。

**优点**：
- 每类来源用最契合的加载模型
- 第 1、2 层（覆盖绝大多数新增需求）不触碰主仓库代码
- 晴发文保持现状，零迁移成本
**缺点**：
- 三条路径并存，认知成本略高（本文档通过明确分类缓解）

## 决策

**选择 C：三层文本源模型。**

按「数据如何到达客户端」划分三类：

```
┌─────────────────────────────────────────────────────────────────┐
│                    TextSourceEntry (config.json)                │
│   loader ∈ {LOCAL_FILE, REMOTE_API, REGISTRY}                   │
│   leaderboard_mode ∈ {NONE, SERVER_RESOLVED, LOCAL_LOOKUP}      │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  ┌──────────┐         ┌────────────┐         ┌────────────┐
  │ 第1层    │         │  第2层     │         │  第3层     │
  │ 本地文件 │         │ Registry   │         │ 即时拉取   │
  │ (静态)   │         │ (脚本工具) │         │ (实时)     │
  └──────────┘         └────────────┘         └────────────┘
   前/中/后五百         每日一文               晴发文 random
   自定义 txt           静态文集               服务端 API
   打词单字             社区 PR 文集            未来带认证源
```

### 三层职责对照

| 维度 | 第 1 层：本地文件 | 第 2 层：开源文库（Registry）| 第 3 层：即时拉取 |
|:---|:---|:---|:---|
| **`loader`** | `LOCAL_FILE` | `REGISTRY` | `REMOTE_API`（+ 独立 Gateway，如晴发文）|
| **数据来源** | 用户/打包 txt | 用户本地运行开源文库脚本生成 JSON | 服务端/第三方实时 API |
| **时效性** | 静态 | 日级/周级延迟可接受 | 秒级，用户实时交互 |
| **数据规模** | 单文件 | 增量、可枚举 | 全库不可枚举（random 模型）|
| **网络韧性要求** | 无 | 低（脚本失败有缓存兜底）| 高（实时）|
| **客户端缓存** | 不需要 | **必须**（兑现 `cache_ttl_seconds`）| 不需要（即时语义）|
| **账号要求** | 无 | 无 | 用户自有账号（`token_store`）|
| **现有实现** | ✅ `QtLocalTextLoader` | ✅ `RegistryTextProvider`（缓存已补）| ✅ `RemoteTextProvider` + 晴发文独立 Pipeline |
| **CI workflow** | 不需要 | 不需要（用户本地运行脚本） | 不需要 |

---

## 第 2 层详化：Registry 脚本工具模型（本 ADR 的核心增量）

### 拓扑

```
┌──────────────────────────────────────────────────────────────┐
│  Registry 仓库（独立 git 仓库，如 open-typing-texts）         │
│  （提供纯脚本工具模板，用户本地运行生成文本）                   │
│                                                              │
│  registry_index.json          ← 声明式索引（轻量元数据）       │
│  content/                                                   │
│    daily.json                ← 每日一文（每日 1 篇）           │
│    gushiwen-300.json         ← 静态文集                       │
│    community-xxx.json        ← 社区 PR                        │
│                                                              │
│  scripts/                                                   │
│    fetch_daily.py            ← 抓取脚本（用户本地运行）       │
└──────────────────────────────────────────────────────────────┘
                         │
                         │ httpx.get() — 客户端只读 JSON
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  typetype 主仓库（客户端）                                    │
│                                                              │
│  RegistryTextProvider                                        │
│    ├─ _fetch_json(url)            [现状：直打网络]            │
│    ├─ _read_cache(key) + ttl      [待补：磁盘缓存层]          │
│    ├─ _write_cache(key, data)     [待补：写缓存]              │
│    └─ stale-while-revalidate      [待补：过期返回旧值+后台刷]  │
└──────────────────────────────────────────────────────────────┘
```

### `registry_index.json` schema

```jsonc
{
  "version": 1,
  "updated_at": "2026-07-05T00:00:00Z",
  "sources": [
    {
      "source_key": "daily",            // 必填，匹配 content/{key}.json
      "label": "每日一文",
      "description": "CI 每日精选",
      "category": "daily",              // UI 分组用
      "update_freq": "daily",           // daily/weekly/static
      "has_ranking": false              // 结构兼容字段：registry 源恒为 SERVER_RESOLVED，此值恒 false 且不参与逻辑（见 §决策-三层职责对照）
    }
  ]
}
```

**设计约束**：
- 索引文件**只放元数据**，正文 lazy 加载（避免索引膨胀）
- `source_key` 校验沿用 `_validate_source_key()`（`registry_text_provider.py:96-98`，禁 `/`、`..`、`\`）
- 正文大小受 `RegistryConfig.max_content_bytes`（默认 1MB）限制

### 用户本地运行脚本的韧性设计

Registry 仓库提供纯脚本工具（`scripts/`），用户本地运行生成 `content/*.json` 和
`registry_index.json`，再通过本地 HTTP 服务（如 `python -m http.server 18888`）暴露给客户端。

**韧性要点**：
- 脚本运行失败不影响客户端（客户端读旧缓存）
- 增量累积：`content/` 目录不清理，每次追加/覆盖
- 客户端兜底：缓存层无视 TTL 返回旧值

### 本地运行的网络与耗时问题

用户本地运行脚本拉源站时的网络/耗时问题，按来源类型差异化处理：

| 来源类型 | 网络风险 | 耗时风险 | 应对 |
|:---|:---|:---|:---|
| 公开数据集（古诗文网 API、Hugging Face、GitHub txt 仓库）| 低 | 低 | 直接 fetch 即可 |
| 每日一文（每日 1 篇）| 低 | 极低 | 每日跑一次脚本 |
| 受风控/限频的源（晴发文类）| **高** | **高** | **不入 Registry，走第 3 层即时拉取** |

### 客户端缓存层补全（**第 1 优先级前置工作**）

`RegistryTextProvider` 当前缓存层是空的（`cache_dir` 创建但无读写）。补全后的请求决策树：

```
fetch_text_by_key(key)
  ├─ cache_hit(key) 且 not expired(TTL)?
  │   → 返回缓存（最快路径）
  ├─ cache_hit(key) 且 expired?
  │   → 返回旧缓存（stale）+ 后台刷新
  │      (前台无延迟，下次命中新值)
  ├─ cache_miss + 在线?
  │   → 依次尝试 primary_url → mirror_url，成功写缓存
  └─ cache_miss + 离线（primary + mirror 均失败）?
      → 返回 stale 缓存（若有，无视 TTL 兜底）；无缓存则返回 None
```

**实现要点**（复用现有 `cache_dir` + `cache_ttl_seconds`）：
- 缓存文件：`{cache_dir}/{key}.json` + `{cache_dir}/_index.json`
- 离线兜底：网络失败时**无视 TTL** 用缓存（关键行为）
- mirror fallback 顺序与 `_fetch_json` 现有双源逻辑一致（`registry_text_provider.py:71-73`、`:79-81`）
- 写缓存用临时文件 + rename（原子写，防半写）
- 后台刷新走 `QtAsyncExecutor`（已有，`src/backend/integration/qt_async_executor.py`）

---

## 第 3 层定位：晴发文保持现状，**不**纳入 Registry

### 为什么晴发文不能 CI 化

| 理由 | 证据 |
|:---|:---|
| API 是即时交互模型 | `/api/texts/random`（`wenlai_provider.py:143`）每次返回不同内容，CI 冻结破坏 random 语义 |
| 无全量/分页接口 | 只有 random + adjacent，攒全库需 N 次 random 去重，撞 GHA 6h 限额 + 触发风控 |
| 违反账号模型 | `/api/auth/login`（`wenlai_provider.py:106`）+ token，CI 持账号 = 账号共享，违反晴发文账号体系 |
| 用户预期实时 | 用户点「再来一篇」等不了 24h |

### 晴发文现状保留

- 独立 Port：`ports/wenlai_provider.py`（含 `WenlaiAuthRequiredError`）
- 独立 Adapter / Gateway / UseCase：`wenlai_provider.py` → `wenlai_gateway.py` → `load_wenlai_text_usecase.py`
- 走 Worker：`presentation/adapters/wenlai_adapter.py` 已用 `_run_worker()`，符合 ADR-005
- token 存储：`integration/secure_token_store.py`

**结论：晴发文是第 3 层的参照实现，保持不动。** 未来若有第 2 个带认证的实时源（如其他打字平台 API），抽象 `AuthenticatedRemoteProvider` Port 时再统一，不预先做（YAGNI）。

---

## 扩展矩阵（落地后新增来源的标准化路径）

| 想加什么 | 走哪层 | 改动量 |
|:---|:---|:---|
| **每日一文** | 第 2 层 | open-typing-texts 仓库提供抓取脚本，用户本地运行生成 `content/daily.json` |
| **古诗文 300 首**（公开数据集）| 第 2 层 | open-typing-texts 仓库写一次性 `fetch_gushiwen.py`，跑一次冻结 |
| **社区贡献文集** | 第 2 层 | 贡献者往 open-typing-texts 仓库 PR 改 `registry_index.json` + `content/*.json`，typetype 主仓不动 |
| **新本地练习文件** | 第 1 层 | `config.json` 加 1 行 `{loader: "local_file", local_path: "..."}`，零代码 |
| **新带认证实时源** | 第 3 层 | 完整一套 Port + Adapter + Gateway + UseCase（参考晴发文）|

**关键收益**：第 1、2 层（覆盖绝大多数新增需求）**完全不触碰主仓库代码**，只需配置或 Registry 仓库 PR。

---

## 落地路线图

按「价值/工作量比」排序，每步可独立验证、独立上线：

### Phase 1：补缓存层（**前置阻塞**，1-2 人日）
- `RegistryTextProvider` 加 `_read_cache` / `_write_cache` / TTL 检查 / 离线兜底
- 兑现 `cache_ttl_seconds` 死字段
- 测试：断网下能读旧缓存

> 工时说明：若仅做同步缓存（cache hit/miss + 离线兜底 + 原子写）约 1 人日；后台刷新（stale-while-revalidate）涉及 `QtAsyncExecutor` 生命周期与并发管理，单独约 1 人日，可拆为 Phase 1a/1b 独立上线。

### Phase 2：建 open-typing-texts 仓库 + 纯脚本工具（核心价值，2-3 人日）
- 建 `open-typing-texts` 仓库，提供抓取脚本模板（见仓库模板：`docs/decisions/registry-repo-template/`）
- 写 `scripts/fetch_daily.py`（源站自定，先接公开 RSS / 古诗文 API）
- **不提供 CI workflow，文本由用户本地运行脚本生成**
- 写 `registry_index.json` schema 文档
- typetype 侧 `config.json` 配 `registry.primary_url`

### Phase 3：catalog 接 UI（1-2 人日）
- catalog worker 优先走 `RegistryTextProvider.get_catalog()`
- fallback 走 leaderboard API（保持兼容）
- 来源选择页展示 registry catalog

### Phase 4：晴发文双轨治理（**可选，长期**）
- 仅当接入第 2 个带认证实时源时启动
- 抽象 `AuthenticatedRemoteProvider` Port
- 不做则保持现状，无技术债利息

---

## 验证清单

落地后逐项核验：

- [ ] `RegistryTextProvider` 缓存层：断网下能读 `cache_dir/{key}.json` 旧值
- [ ] `cache_ttl_seconds` 配置项生效（改值后缓存命中行为变化）
- [ ] Registry 仓库 `registry_index.json` 通过 GitHub Pages 可访问
- [ ] 每日 workflow 连跑 3 天，`content/daily.json` 按日更新
- [ ] workflow 单日失败（手动模拟）后，第二天能继续，客户端读旧值无崩
- [ ] `config.json` 配 `daily` source 后，客户端能从 registry 拉到当天内容
- [ ] catalog 接 UI 后，来源选择页展示 registry 全部条目
- [ ] `ARCHITECTURE.md` 文本源章节更新三层模型
- [ ] `docs/reference/config.md` 补 registry schema 说明
- [ ] `AGENTS.md §8` 加新陷阱：Registry 必须读缓存、晴发文不得 CI 化

---

## 反模式（明确不做）

| 反模式 | 不做原因 |
|:---|:---|
| ❌ 客户端执行远程脚本 | RCE 面，威胁 token（`secure_token_store.py`）/ 键盘监听（`global_key_listener.py`）/ SQLite 统计库 |
| ❌ 晴发文 CI 化 | 违 random 语义、违账号模型、API 无全量接口 |
| ❌ 把晴发文塞进 `TextSourceConfig.sources` | 它需要登录态/换段/token，简单 `source_key` 承载不了 |
| ❌ Registry catalog 走主线程 | 违 ADR-005（`005-all-text-load-via-worker.md`），UI 必崩 |
| ❌ Registry 直打网络无缓存 | 弱网/离线即崩，`cache_ttl_seconds` 死字段 |
| ❌ 预先抽象 `AuthenticatedRemoteProvider` | YAGNI，第 2 个实时源未出现前不抽象 |

---

## 一句话总结

**三层模型，按数据如何到达客户端分而治之**：本地文件零成本、Registry 走用户本地脚本生成的 JSON（补缓存 + 建 Registry 仓库即可上线，晴发文除外）、即时拉取保持 Worker 实时（晴发文现状不动）。三层各自有明确的扩展路径和扩展成本，**第 1、2 层的新增需求不再触碰主仓库代码**——这是本架构的核心收益。
