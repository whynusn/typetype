# OTT 去中心化源生态：三仓库架构分析

<!-- 状态: active | 创建: 2026-08-12 | 关联: ADR-010, ADR-011 -->

> 本文分析 `open-typing-texts`、`ott-source-hub`、`typetype` 三个仓库的定位、区别与联系，并评估当前架构的合理性。

---

## 一、三仓库定位一览

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────────────┐     ┌──────────────────────┐             │
│  │  open-typing-texts   │     │   ott-source-hub     │             │
│  │  ──────────────────  │     │   ────────────────   │             │
│  │  "宪法 + 工厂手册"    │     │   "源集合"           │             │
│  │                      │     │                      │             │
│  │  • OTT Core v1 协议  │     │  • ott-repo.json     │             │
│  │  • OTT Repo v1 规范  │     │  • 适配器包目录       │             │
│  │  • JSON Schema 定义  │     │  • 贡献指南          │             │
│  │  • 参考适配器实现     │     │                      │             │
│  │  • 抓取脚本模板      │     │  （纯清单，不托管    │             │
│  │                      │     │   任何文本内容）       │             │
│  │  不提供/不分发/不托管 │     │                      │             │
│  │  任何文本内容         │     │                      │             │
│  └──────────┬───────────┘     └──────────┬───────────┘             │
│             │                            │                         │
│             │  协议定义                   │  协议消费                │
│             │  (被引用)                   │  (被订阅)                │
│             │                            │                         │
│             └──────────┬─────────────────┘                         │
│                        │                                           │
│                        ▼                                           │
│             ┌──────────────────────┐                               │
│             │     typetype         │                               │
│             │     ──────────       │                               │
│             │     "客户端/壳"       │                               │
│             │                      │                               │
│             │  • 独立实现协议消费   │                               │
│             │  • 不 import 协议仓   │                               │
│             │  • 只读 OTT 协议     │                               │
│             │  • 沙箱执行 L3       │                               │
│             │  • 联邦聚合多 repo   │                               │
│             └──────────────────────┘                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1. `open-typing-texts` — 协议规范 + 参考实现

**一句话**：定义"语言"是什么，并提供一个"官方示例工厂"。

| 维度 | 内容 |
|:---|:---|
| **核心文件** | `OTT_SPEC.md`（Core v1 数据面）、`docs/repo-manifest-spec.md`（Repo v1 控制面）、`schemas/*.json`（7 个 JSON Schema） |
| **参考适配器** | `ott_adapter/` — 一个完整的 Python HTTP 服务器，实现 Service Profile + Static Profile + Admin Profile |
| **脚本模板** | `scripts/fetch_poem.py` — 本地抓取脚本示例；逆向源统一走 `ott-source-hub` L1.5 DSL 规则 |
| **明确不提供** | 任何文本内容。README 三次声明"不提供、不分发、不托管" |
| **版本** | OTT Core `1.0` + OTT Repo `1.1` + Adapter `0.5.0` |

**类比**：相当于 HTTP 协议族（RFC 7230 等）+ Nginx 参考实现。它定义协议标准，附带一个可用的参考服务器，但**不运营任何网站**。

### 2. `ott-source-hub` — 源仓库（去中心化生态的"源集合"）

**一句话**：一份可订阅的"源清单"，列出所有可用的文本来源。

| 维度 | 内容 |
|:---|:---|
| **核心文件** | `ott-repo.json` — OTT Repo v1 manifest |
| **sources[]** | 混合四种类型：ott-instance（端点）、ott-rule（声明式规则）、ott-bridge（桥接）、ott-script（脚本） |
| **adapters/** | 每个源独立目录（adapter.json + script.py + fixtures） |
| **明确不提供** | 文本正文内容（只托管清单和规则/脚本） |
| **设计来源** | 直接遵循 `open-typing-texts/docs/repo-manifest-spec.md` |

**类比**：相当于 mihon 的 extension repo、legado 的订阅链接、Chrome Web Store。它是一个"应用商店"，只列应用，不存应用的内容数据。

### 3. `typetype` — 客户端（壳软件）

**一句话**：一个"真空壳"打字应用，所有外部内容通过 OTT 协议订阅。

| 维度 | 内容 |
|:---|:---|
| **核心能力** | 打字统计、成绩提交、薄弱字分析、文本加载 |
| **OTT 消费** | `OttTextProvider`（Core v1 数据面）+ `OttFederationProvider`（Repo v1 控制面联邦聚合） |
| **L3 沙箱** | `ScriptSandbox` + `ott_script_runner.py`（子进程隔离 + AST 白名单 + Landlock + seccomp） |
| **本地缓存** | `RepoManifestCache` + `ScriptCache`（TTL + stale-while-revalidate + 原子写） |
| **不依赖** | **不 import `open-typing-texts`** — 零代码依赖，仅通过协议文档引用 |

**类比**：相当于 mihon 客户端、Firefox 浏览器、legado 阅读客户端。它消费协议，但不定义协议。

---

## 二、三者之间的联系

### 联系 1：协议引用（文档级，非代码级）

```
open-typing-texts (定义协议)
    │
    │  OTT_SPEC.md ←── typetype/ott_repo_manifest.py 注释引用
    │  repo-manifest-spec.md ←── typetype/ott_script_safety.py 注释引用
    │  schemas/ott-repo.schema.json ←── typetype CI 校验引用
    │
    │  (typetype 不 import open-typing-texts 任何代码)
    │
    ▼
typetype (独立实现协议消费方)
```

**关键发现**：typetype 和 open-typing-texts 之间**没有代码依赖**。typetype 是自己重新实现了 OTT Core v1 和 Repo v1 的消费逻辑。协议仓的 schema 文件被 typetype 的 CI 引用做校验，但运行时完全独立。

### 联系 2：订阅关系（运行时）

```
ott-source-hub (源清单)
    │
    │  ott-repo.json URL
    │  (用户手动订阅)
    │
    ▼
typetype (客户端)
    │
    ├─ RepoManifestCache → HTTP GET → 缓存 manifest
    ├─ OttFederationProvider → 遍历 sources[] → 联邦聚合
    │     ├─ ott-instance → OttClient → /ott/v1 读取
    │     ├─ ott-rule → OttRuleInterpreter → 声明式执行
    │     └─ ott-script → ScriptSandbox → 子进程执行
    │
    ▼
用户打字
```

### 联系 3：安全边界

```
open-typing-texts                ott-source-hub                typetype
(定义安全规则)                   (声明安全需求)                (执行安全强制)
─────────────────         ─────────────────         ─────────────────
• script_safety.py          • adapter.json              • ScriptSandbox
  AST 白名单                    permissions.network        子进程隔离
  import 黑名单                 rights.min_api_level       256MB/30s/Landlock
• repo-manifest-spec         • trust.pubkey              • TOFU + 固定公钥
  签名 canonical                                    • 撤销列表
```

---

## 三、完整数据流

### 加载一条文本打字

```
用户在载文中心点了一篇文本
    ↓
appBridge.requestLoadText(sourceKey)
    ↓
TextAdapter（Presentation 层）
    ↓
LoadTextUseCase.plan_load(sourceKey)  ← 决定走哪个 Gateway
    ↓
TextSourceGateway → 根据 loader 字段路由：
    ├─ LOCAL_FILE   → QtLocalTextLoader（读本地 .txt）
    ├─ REGISTRY     → OttTextProvider → OttFederationProvider
    │                    ↓
    │               先查缓存 → 有且新鲜 → 直接返回
    │               缓存过期 → 返回旧缓存 + 后台刷新
    │               无缓存  → HTTP GET 仓库 → 写入缓存 → 返回
    │                             ↓
    │                        失败 → 走镜像 URL
    │                        全失败 → 离线兜底（用旧缓存）
    └─ REMOTE_API   → RemoteTextProvider → typetype-server
    ↓
TypingPage.applyLoadedText() → 显示在打字区
```

### 订阅数据流

```
config.json.source_repos[]
    │
    ├─ RepoManifestCache.get_manifest(repo)
    │     ├─ cache hit fresh → 返回
    │     ├─ cache hit stale → 返回缓存 + 后台刷新
    │     └─ miss → HTTP GET url → validate_repo_manifest() → 原子写
    │
    └─ OttFederationProvider.list_all_entries()
          └─ 遍历 enabled repos → manifest.sources[type=ott-instance]
                └─ 每 authority 建 _InstanceClient（OttClient × endpoints）
                      └─ priority 排序 + 健康度指数退避 failover
                            └─ 合并条目（authority 命名空间去重）
```

### 打字统计链路

```
物理按键 → evdev（Linux）/ Quartz（macOS）
    ↓
GlobalKeyListener → keyPressed 信号
    ↓
TypingAdapter.handlePressed()
    ↓
TypingService.accumulate_key()  ← 计算码长、击键、键准
    ↓
CharStatsService.accumulate()
    ↓
flush_async() → SQLite 持久化（本地 .db 文件）
```

---

## 四、文本数据的来源（3 层模型）

```
  第 1 层（本地文件）        第 2 层（开源文库）           第 3 层（即时拉取）
  ┌──────────────┐      ┌───────────────────┐       ┌────────────────┐
  │ 剪贴板        │      │ OTT Repo 订阅      │       │ typetype-server│
  │ 自定义载文     │      │ ┌─ L0: 数据实例    │       │  文本列表       │
  │ 前/中/后五百   │      │ ├─ L1: 声明式规则  │       │ 晴发文 API     │
  │ 内置示例      │      │ ├─ L1.5: DSL 引擎  │       │ AI 智能推荐    │
  │ 本地文库      │      │ ├─ L2: 桥接(未落地) │       └────────────────┘
  │ 练单器        │      │ └─ L3: 脚本沙箱    │
  └──────────────┘      └───────────────────┘
       ↑                       ↑                        ↑
  零网络依赖              可离线缓存                  实时交互
  静态内容                TTL + 后台刷新              需账号/Token
```

**关键区分**：
- **第 1 层**：文本打包在 app 里或用户本地，永不需要网络
- **第 2 层**：第三方 OTT 仓库（如 `ott-source-hub`），有缓存，可离线使用
- **第 3 层**：每次用实时请求（晴发文、极速杯），必须有网

---

## 五、数据在用户本地停留吗？

**会停留，但分层管理**：

| 数据 | 停留位置 | 停留多久 | 用途 |
|:---|:---|:---|:---|
| **OTT manifest 缓存** | `~/.config/typetype/cache/repos/{repo_id}/manifest.json` | TTL（默认 1h），过期后台刷新 | 离线可继续用 |
| **OTT 条目缓存** | `~/.config/typetype/cache/repos/{repo_id}/entries/{entry_id}.json` | 同上 | 文本内容离线可打 |
| **L3 脚本缓存** | 同上 `scripts/{hash}.py` | TTL + AST 校验 | 脚本离线可执行 |
| **L3 脚本执行结果** | 内存（不持久化） | 会话期间 | 当次载文用 |
| **打字统计** | `~/.config/typetype/stats.db`（SQLite） | **永久** | 薄弱字分析、历史记录 |
| **成绩记录** | 本地 + 服务端（如果提交了） | 永久 | 排行榜展示 |
| **订阅列表** | `config.json.source_repos[]` | 永久（用户管理） | 控制面 |
| **TOFU 公钥** | `config.json.source_repos[].pinned_pubkey` | 永久（首次信任后固定） | 防中间人 |
| **屏蔽列表** | `config.json.blocked_content_hashes[]` | 永久（用户/撤销列表） | 内容审核 |

**设计原则**：
- 网络来的内容**只缓存**，不默认执行
- L3 脚本**必须先签名验证 + TOFU 确认**才缓存和执行
- 离线时**读缓存兜底**（无视 TTL），不打网络
- 用户**随时可清除**所有缓存（设置页一键操作）

---

## 六、四级信任模型

| 层级 | 形态 | 客户端是否执行代码 | 签名要求 |
|:---|:---|:---|:---|
| **L0** | OTT 数据实例（纯 JSON 文本） | ❌ 零执行 | 可选（仅作 UI 信任徽章） |
| **L1** | 声明式规则（JSON path/正则） | ✅ 受限解释器 | 可选 |
| **L1.5** | DSL 引擎（45 原语，无循环） | ✅ 白名单求值器 | 可选 |
| **L3** | Python 脚本（沙箱） | ✅ 子进程隔离 | ✅ **必须签名 + TOFU 确认** |

**关键不变式**：L0/L1/L2 内容**永远没有代码执行面**。L3 脚本在子进程沙箱内执行（256MB 内存 / 30s CPU / Landlock 文件系统隔离 / seccomp 系统调用过滤），逃逸不突破进程边界。

---

## 七、架构合理性评估

### ✅ 合理之处

#### 1. 三仓分离 = 法律免疫

| 仓 | 角色 | 法律地位 |
|:---|:---|:---|
| `open-typing-texts` | 协议规范 + 参考实现 | 纯技术文档，零内容 |
| `ott-source-hub` | 源清单 | 只列规则/脚本，不托管文本 |
| `typetype` | 客户端 | 零内置第三方内容 |

**三个仓都不持有版权内容**。文本数据由用户本地运行脚本生成（L3）或从第三方 OTT 实例获取（L0）。即使某个源被投诉，只需从 `ott-source-hub` 移除该条目，客户端通过撤销列表自动屏蔽。

对标 mihon 在 DMCA 后的生存策略——应用与内容彻底分离。

#### 2. 协议独立演进

OTT Core v1（数据面）和 OTT Repo v1（控制面）**独立版本号**。Core 稳定后，Repo 可以独立升级而不破坏现有客户端。这是 ADR-010 的核心决策，避免了"统一大协议"的重写风险。

#### 3. 信任分级（L0-L3）

每一层都有明确的安全边界和签名要求。L0/L1/L2 永远无代码执行面；L3 逃逸不突破进程边界。

#### 4. 多 repo 联邦聚合

`OttFederationProvider` 支持同时订阅多个 repo，按 authority 命名空间隔离。一个 repo 挂了自动 failover 到镜像。这比 legado 的单点订阅健壮得多。

---

### ⚠️ 潜在问题与改进空间

#### 1. typetype 和 open-typing-texts 的代码重复

**现状**：typetype 的 `ott_script_safety.py` 注释写着"复用 open-typing-texts `script_safety.py` 的检查逻辑"，但实际上是**各自独立实现**的。

**风险**：两处实现可能漂移（drift）。如果 open-typing-texts 更新了安全检查逻辑（如新增 `__subclasses__` 拦截），typetype 可能没有同步跟进。

**建议**：
- 方案 A（激进）：typetype 直接依赖 open-typing-texts 作为 Python 包（`uv pip install git+https://...`），运行时 import 其 `script_safety` 模块
- 方案 B（保守）：保持独立实现，但在 CI 中增加"交叉验证"步骤——用 open-typing-texts 的 `ott_adapter` 对 typetype 的 L3 脚本做独立校验，确保两处 AST 检查结果一致

#### 2. Schema 同步问题

**现状**：`open-typing-texts/schemas/ott-repo.schema.json` 是权威 schema，typetype 在 CI 引用它。但 typetype 的 `resources/ott-repo/ott-repo.json`（内置离线源）是独立维护的。

**风险**：如果 schema 升级（如 Repo v1.1 → v1.2 新增字段），typetype 的内置源可能不通过新 schema 校验。

**建议**：typetype 的 CI 应该从 open-typing-texts 仓动态拉取最新 schema，而不是硬编码引用。

#### 3. `ott-source-hub` 的"空壳"问题

**现状**：`ott-source-hub` 刚刚创建，`sources[]` 为空。它的价值取决于能否填充足够多的源。

**风险**：如果长期空仓，用户订阅后看不到任何内容，生态冷启动失败。

**建议**：优先迁移 2-3 个现有源（如一言 hitokoto、古诗文）作为初始内容，证明仓库可用。

#### 4. L2 ott-bridge 的"未落地"状态

**现状**：ADR-011 的 3.5 选择"明示暂不开放"，订阅面板显示"桥接源暂不支持"。

**影响**：晴发文（wenlai）是 typetype 实际使用的带认证实时源，但它走的是**独立 Pipeline**（`WenlaiProvider → WenlaiGateway → LoadWenlaiTextUseCase → WenlaiAdapter`），不走 OTT 协议。

**问题**：这意味着 OTT 协议目前无法覆盖"带认证的实时源"这一重要场景。如果未来要把晴发文纳入 OTT 生态，需要补上 L2。

**建议**：短期保持现状（晴发文独立 Pipeline 工作良好），中期评估 L2 的需求优先级。

#### 5. 发现机制缺失

**现状**：OTT Repo v1 定义了 Directory（repo-of-repos）概念，但**未实现**。用户只能靠口口相传获得 repo URL。

**影响**：生态冷启动困难。新用户不知道有哪些源可用。

**建议**：Phase 7 的 Directory 实现应该提前。一个简单的 JSON 文件列出社区已知的 repo URL 即可。

#### 6. 签名互操作的"自我参照"

**现状**：`ott-source-hub` 的 `ott-repo.json` 已使用 Ed25519 签名，L3 脚本源具备签名准入条件。签名私钥只保存在维护者本地配置目录，不进入仓库。

**剩余问题**：当前发布仍依赖维护者本地签名操作；私钥丢失会触发公钥轮换，并使已固定旧公钥的客户端进入 `pending`。

**建议**：后续配置 GitHub Actions 签名流水线时，将私钥放入仓库级 Secret，并保留人工审批/受保护环境，避免普通 PR 获得签名权限。

---

## 八、总结判断

| 维度 | 评价 | 说明 |
|:---|:---|:---|
| **法律风控** | ⭐⭐⭐⭐⭐ | 三仓分离 + 零内置内容，对标 mihon 生存策略 |
| **协议设计** | ⭐⭐⭐⭐ | Core/Repo 独立版本，信任分级清晰 |
| **代码复用** | ⭐⭐⭐ | 协议仓和客户端各自独立实现，有漂移风险 |
| **生态就绪度** | ⭐⭐ | 协议完备但源仓库空、发现机制缺失 |
| **安全纵深** | ⭐⭐⭐⭐⭐ | L0-L3 分级 + 沙箱多层防线 + 撤销列表 |
| **可互操作性** | ⭐⭐⭐ | schema 统一但运行时各自实现 |

**结论**：架构设计**方向正确、分层合理**，当前最大的风险不是设计缺陷，而是**生态冷启动**——`ott-source-hub` 需要尽快填充初始内容，Directory 发现机制需要提前实现。协议层的重复代码问题可以通过 CI 交叉验证缓解，不需要急于合并为单一依赖。

---

## 九、参照系对比

| 参照 | 学什么 | 不学什么 |
|:---|:---|:---|
| **mihon** | 应用零内置源；repo 即 URL；多 repo 并存；默认不信任、显式启用 | APK 可执行扩展模式（签名/审核/兼容性负担，且 mihon 被 DMCA 后证明可执行物是法律攻击面） |
| **kazumi** | 规则是 JSON 数据（≤5 行选择器）；API level 版本协商；索引 CI 自动生成 | 单仓托管规则的 GitHub 依赖（风控即瘫，见其 issue #414）→ 我们要多镜像 |
| **legado** | 订阅链接返回源列表并自动刷新；任何人可维护合集 | 书源格式无版本治理导致的碎片化（规则互不兼容、质量参差）→ 我们要 schema + 兼容测试包 |
