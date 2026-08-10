# 去中心化文本源生态设计（OTT Federation）

<!-- 状态: active | 创建: 2026-07-26 | 最后验证: 2026-08-10 | 关联: ADR-008, ADR-009, ADR-010, ADR-011 -->

> 目标：在 OTT Core v1 数据面之上，补齐**控制面**（订阅、信任、发现），使 typetype 成为类似 mihon / kazumi / 开源阅读（legado）的去中心化内容生态客户端：任何人可发布文本源，任何用户可自由订阅，协议不设权威中心。
>
> 核心判断：**OTT Core v1 不需要推翻**。它作为数据面（条目模型、分段分发、revision、内容 hash）是合格的。当前的缺口全部在控制面——客户端只能订阅单一 authority、没有"源仓库"概念、没有信任分级、没有发现机制。本设计新增独立的 **OTT Repo** 协议构件承载控制面，Core v1 保持不变。

---

## 目录

- [1. 缺口分析](#1-缺口分析)
- [2. 设计哲学](#2-设计哲学)
- [3. 概念模型](#3-概念模型)
- [4. OTT Repo 协议构件](#4-ott-repo-协议构件)
- [5. 信任与安全模型](#5-信任与安全模型)
- [6. 身份、寻址与进度](#6-身份寻址与进度)
- [7. 客户端架构演进](#7-客户端架构演进)
- [8. 发现与治理](#8-发现与治理)
- [9. 协议演进治理](#9-协议演进治理)
- [10. 分阶段路线](#10-分阶段路线)
- [11. 场景自检](#11-场景自检)
- [12. 远期方向（明确不做进 v1）](#12-远期方向明确不做进-v1)

---

## 1. 缺口分析

### 1.1 现有资产（保持不变）

| 资产 | 位置 | 评价 |
|:---|:---|:---|
| OTT Core v1 数据模型（Source / EntrySummary / EntryDetail / Segment） | open-typing-texts `OTT_SPEC.md` | 合格的数据面，不动 |
| Static Profile（纯静态文件分发，可托管 GitHub Pages） | 同上 | 去中心化分发的关键能力，已是亮点 |
| Service Profile（`/ott/v1` 只读 API） | 同上 | 动态实例形态，不动 |
| 进度键 `ott:{authority}:{entry_id}@{revision_id}` | ADR-009 + `ott_segment_provider.py` | authority 命名空间是多实例的种子 |
| 抓取脚本 AST 安全检查 | open-typing-texts `script_*_safety.py` | L3 脚本源的现有防线 |
| trait 能力机制（15 项能力 flags） | PR #44 `TextSourceBehaviors.js` | 异构源的前端承接机制，直接复用 |
| 法律隔离（协议仓 / 内容仓 / 客户端三分离） | 两仓现状 | 对标 mihon 的生存底线，已满足 |

### 1.2 真正的缺口（控制面）

> 设计时快照（2026-07-26）；所列缺口已由 ADR-011 Phase 1-3 全部关闭，保留此表仅作背景参考。

| 缺口 | 现状 | 后果 |
|:---|:---|:---|
| 单 authority 配置 | `RegistryConfig` 只有一个 `primary_url` + 一个 `mirror_url`（同一仓的 CDN） | 用户无法同时订阅多个文本源实例 |
| 无"源仓库"概念 | mihon 的 extension repo、legado 的订阅链接、kazumi 的规则仓库都是**可分发的源清单**，OTT 无对应物 | 源无法被打包传播，生态无法形成 |
| 无信任模型 | 源的形态（纯数据 / 声明式规则 / 可执行脚本）没有分级 | 风险敞口无设计，要么过度防御要么过度开放 |
| 无发现机制 | 新实例只能靠口口相传完整 URL | 生态冷启动困难 |
| authority 未升格 | 只是进度键前缀，无身份规范、无镜像、无验证 | 多实例下身份冲突与进度漂移无保障 |

### 1.3 参照系教训

| 参照 | 学什么 | 不学什么 |
|:---|:---|:---|
| mihon | 应用零内置源；repo 即 URL；多 repo 并存；默认不信任、显式启用 | APK 可执行扩展模式（签名/审核/兼容性负担，且 mihon 被 DMCA 后证明可执行物是法律攻击面） |
| kazumi | 规则是 JSON 数据（≤5 行选择器）；API level 版本协商；索引 CI 自动生成 | 单仓托管规则的GitHub 依赖（风控即瘫，见其 issue #414）→ 我们要多镜像 |
| legado | 订阅链接返回源列表并自动刷新；任何人可维护合集 | 书源格式无版本治理导致的碎片化（规则互不兼容、质量参差）→ 我们要 schema + 兼容测试包 |

---

## 2. 设计哲学

1. **应用与内容彻底分离**：客户端零内置源，官方永不托管内容（内置 `file://` 离线快照除外，ADR-011 Phase 4）。这是 mihon 在 DMCA 后存活的铁律，也是本生态的法律免疫层。
2. **订阅而非内置**：一切皆 URL。用户显式添加、可随时移除；客户端不替用户做价值判断。
3. **声明式优于可执行**：规则是数据不是代码。L3 抓取脚本（Python）经 Repo 分发但必须过签名门槛（ADR-011 决策 3）；L0/L1/L2 保持纯数据。
4. **多实例无中心**：任何人可跑实例、可维护目录。协议不设权威注册表，官方目录只是可选默认之一。
5. **渐进信任**：默认不信任，能力分级决定风险敞口；L0/L1/L2 签名是信任信号（徽章）；L3 签名是执行门槛（ADR-011 决策 3）。

---

## 3. 概念模型

三层实体，自上而下逐层可选：

```
Directory（目录，可选）          ← repo-of-repos，发现层
  └─ Repo（源仓库 / 订阅）       ← 可分发的源清单，控制面核心
       └─ Instance / Rule / Bridge / Script（源）  ← 具体文本来源
            └─ Entry / Segment（条目）    ← OTT Core v1 数据面（已有）
```

| 层 | 实体 | 定义 | 类比 |
|:---|:---|:---|:---|
| 发现 | Directory | 一份 Repo Manifest（`type: "directory"`），列出多个 repo 订阅地址 | mihon 社区 repo 列表站、legado 合集站 |
| 控制 | Repo | 一份 Repo Manifest（`ott-repo.json`），列出一组源及其镜像、信任、版本要求 | mihon extension repo、legado 订阅链接、kazumi 规则仓 |
| 数据 | Instance | 一个 OTT 端点（Static 或 Service Profile），有稳定 `authority_id` + 镜像端点列表 | —（OTT Core v1 已有） |
| 数据 | Rule | 内联声明式抓取规则，由客户端内置解释器执行 | kazumi 规则、legado 书源 |
| 数据 | Bridge | 即时 API 桥（如晴发文），凭据本地持有 | legado 登录书源 |
| 数据 | Script | 抓取脚本（L3），子进程沙箱执行，需签名门槛（ADR-011 决策 3） | mihon extension（法律攻击面，故用沙箱） |

约束：

- Directory 只允许引用 Repo，**不允许嵌套 Directory**（防递归解析与循环引用）。
- Repo 中四种源类型可混合；Repo 本身不托管任何文本内容（只托管清单）。
- 每一层都是纯数据（JSON），无任何可执行内容（L3 脚本除外，见 §5.1）。

---

## 4. OTT Repo 协议构件

> 协议细节见 open-typing-texts 仓 `docs/repo-manifest-spec-draft.md`（OTT Repo v1 草案）。此处给出客户端视角的摘要。

### 4.1 Repo Manifest 示例

```json
{
  "protocol": "ott-repo",
  "version": "1.0",
  "type": "repository",
  "repo_id": "texts.example.org",
  "name": "示例中文文库",
  "description": "维护者精选的中文打字文本",
  "maintainer": { "name": "someone", "homepage": "https://example.org" },
  "license": "CC-BY-SA-4.0",
  "updated_at": "2026-08-01T00:00:00+08:00",
  "mirrors": [
    { "url": "https://texts.example.org/ott-repo.json", "priority": 1 },
    { "url": "https://cdn.jsdelivr.net/gh/user/repo@main/ott-repo.json", "priority": 2 }
  ],
  "trust": {
    "signature": "ed25519:<128 hex>",
    "pubkey": "ed25519:<64 hex>",
    "required": false
  },
  "requires": {
    "ott_core": ">=1.0",
    "client_features": ["segmented_content"]
  },
  "sources": [
    {
      "type": "ott-instance",
      "authority": "texts.example.org",
      "label": "示例静态文库",
      "endpoints": [
        { "url": "https://texts.example.org/ott/", "profile": "static", "priority": 1 },
        { "url": "http://127.0.0.1:18888/", "profile": "service", "priority": 2 }
      ],
      "tags": ["chinese", "curated"],
      "default_enabled": true
    }
  ]
}
```

### 4.2 四种源类型

| 类型 | 说明 | 执行面 | 进度 authority |
|:---|:---|:---|:---|
| `ott-instance` | 指向 OTT Static/Service 端点，可列多镜像 | 零执行（纯数据） | instance 声明的 `authority_id` |
| `ott-rule` | 内联声明式规则（请求模板 + 提取器 + 调度） | 客户端内置受限解释器（无任意代码） | `rule:{repo_id}:{rule_id}` |
| `ott-bridge` | 即时 API 桥（wenlai 类） | 协议化 adapter，凭据本地持有 | `bridge:{bridge_kind}` |
| `ott-script` | 抓取脚本（L3） | 子进程沙箱（AST 白名单 + 资源限制 + 进程隔离），需签名门槛（ADR-011 决策 3） | `ott:script:{entry_id}@{revision_id}`（参考 ARCHITECTURE.md § L3） |

### 4.3 声明式规则（L1）的能力边界

规则只允许以下声明式字段，客户端解释器无图灵完备性：

- `request`：URL 模板（支持 `{page}` 等参数插值）、method（仅 GET/POST）、headers 白名单
- `extract`：三选一——JSON path / 正则（带命名组）/ CSS 选择器
- `transform`：固定管道操作（trim、replace、truncate），不可组合出任意计算
- `schedule`：拉取频率（manual/hourly/daily）与缓存 TTL
- `pagination`：页参数名、起始值、步进、上限

明确禁止：任意 JS、动态 URL 计算、回调、任意文件/网络访问。这保证 L1 规则与 L0 数据实例具有同等安全等级——kazumi 已证明该表达力足够覆盖绝大多数文本源。

---

## 5. 信任与安全模型

### 5.1 四级能力模型

| 级 | 形态 | 执行面 | 风险 | 订阅策略 |
|:---|:---|:---|:---|:---|
| L0 | OTT 数据实例 | 零执行 | 仅内容本身的真实性 | 订阅即用 |
| L1 | 声明式规则源 | 受限解释器，无任意代码 | 同上 | 即用，UI 标注"规则源" |
| L2 | 桥接源（即时 API） | 协议化 adapter | 凭据泄露面（凭据仅存本地系统密钥环） | 需用户显式配置凭据 |
| L3 | 抓取脚本（Python） | 子进程沙箱（AST 白名单 + 资源限制 + 进程隔离） | 代码执行面（沙箱内） | **允许经 Repo 分发**；脚本在独立 Python 子进程中执行，逃逸不突破进程边界 |

关键不变式：**客户端从网络订阅的 L0/L1/L2 内容无任意代码执行面；L3 脚本在子进程沙箱内执行，逃逸仅影响子进程**。L3 脚本可经 Repo 分发或放入用户本地 `scripts/` 目录。

### 5.2 签名与验证

- Repo 维护者用裸 Ed25519 对 manifest 签名（minisign 已移除，ADR-011 决策 12）；`trust.pubkey` 随 manifest 发布，首次订阅时 TOFU（trust-on-first-use）固定，后续公钥变更必须显式提醒用户。
- 客户端 UI 显示"已验证 / 待确认 / 未验证 / 验证失败"徽章。**L0/L1/L2 签名不作为准入门槛**——强制证书制会杀死长尾生态（mihon 官方扩展仓之死正是过度中心化的教训）；**L3 例外：签名是执行门槛**（仅 `trust_state=verified` 的仓库执行，ADR-011 决策 3）。
- 实例级完整性由 OTT Core v1 已有的 `content_hash`（sha256）保证，覆盖传输篡改。

### 5.3 威胁模型回答

| 攻击 | 缓解 |
|:---|:---|
| 恶意 repo 提供伪造文本 | 无法执行代码；徽章 + 用户移除 + 客户端内置 blocklist（可选更新） |
| 传输中篡改内容 | `content_hash` 校验 + HTTPS 镜像优先 |
| 伪装他人 authority | 签名 repo 的 authority 与公钥绑定；未签名 authority 冲突时客户端并列展示来源 repo，由用户选择 |
| 规则源探测内网 | `request.url` 仅允许 http(s) 公网 scheme，禁 file:// 与环回/保留地址段（实现期逐条落实） |
| repo 投毒大量垃圾源 | 源在 UI 按 repo 分组展示，一键禁用整个 repo |

---

## 6. 身份、寻址与进度

### 6.1 authority 身份规范

`authority_id` 升格为一等身份，三种合法形式：

| 形式 | 适用 | 示例 |
|:---|:---|:---|
| 反向域名 | 有域名/有 GitHub Pages 的发布者 | `org.example.texts`、`io.github.user.repo` |
| 公钥指纹 | 无域名的签名发布者 | `key:ed25519:a1b2c3...`（指纹前 24 hex） |
| `local` | 本机 adapter 默认 | `local` |

实例在其 `ott.json`（Static）与 `/ott/v1/capabilities`（Service）中**可选**声明 `authority_id`；未声明时客户端回退为主 endpoint 的 host。该字段是对 Core v1 的**向后兼容增量**（旧客户端忽略未知字段）。

### 6.2 条目 URN

现有进度键正式化为全场景通用 URN：

```text
ott:{authority}:{entry_id}@{revision_id}
```

消费场景：打字进度、收藏、历史记录、薄弱字关联、分享链接。多实例下同一 `entry_id` 天然隔离；同一 authority 内容修订（revision 变化）时旧进度保留、新 revision 从零开始（现状语义不变）。

### 6.3 分享与导入

- 深链格式：`ott://{authority}/{entry_id}`
- 客户端解析路径：已订阅含该 authority 的 repo → 直接定位条目；未订阅 → 通过实例 `ott.json` 中的可选 `repo_url` 回指字段找到其所在 repo，提示"发现新实例，是否订阅其来源仓库"。
- repo 本身也可分享：`ott-repo://{url}` 或裸 URL 粘贴导入。

---

## 7. 客户端架构演进

> 本节为方向性设计，不含实现。所有演进遵循 ADR-008/009 的层次约束（Presentation → Application，UseCase 编排，异常走 `GlobalExceptionHandler`）。

### 7.1 配置模型

`RegistryConfig`（单 authority）演进为订阅列表 `SourceReposConfig`：

```json
{
  "source_repos": [
    {
      "url": "https://texts.example.org/ott-repo.json",
      "enabled": true,
      "trust_state": "verified | unverified | failed",
      "pinned_pubkey": "ed25519:...",
      "refresh_ttl_seconds": 86400,
      "etag": "...",
      "added_at": "2026-08-01T00:00:00+08:00"
    }
  ]
}
```

旧 `registry.primary_url` 在加载时自动迁移为一条等价订阅（沿用 `TextSourceEntry` 旧 schema 自动迁移的先例）。`RuntimeConfig` 仍是 config.json 唯一序列化者。

### 7.2 聚合层

- 新增 repo 拉取与缓存组件（复用 `ott_cached_fetcher.py` 的 TTL/stale/原子写/后台刷新模式；manifest 缓存键按 repo URL）。
- `OttTextProvider` 之上引入联邦目录聚合：合并所有启用 repo 的 sources/entries，按 authority 命名空间隔离；同一条目多镜像按 priority + 健康度（近期失败指数退避）failover。
- 每实例仍由现有 `OttClient`（Service→Static 读取顺序）承载，聚合层只做路由不重复实现协议细节。

### 7.3 能力合成与 UI

- trait 合成：repo manifest 声明 × instance `capabilities` features → PR #44 的 15 项 trait flags；`TextSourceBehaviors.js` 注册表从静态配置改为运行时合成。
- 载文中心新增"源仓库"管理页：添加 URL / 粘贴分享串、启用开关、手动刷新、信任徽章、按 repo 分组的源列表。
- 所有 manifest 拉取与聚合走 Worker（ADR-005 文本加载统一走 Worker 的约束不变）。

---

## 8. 发现与治理

### 8.1 发现路径（三条，全部可选）

1. **默认目录**：客户端内置一个官方维护的 directory 订阅，可在设置中关闭或替换——避免硬中心。
2. **社区目录**：任何人可发布 directory（格式同 Repo Manifest，`type: "directory"`），靠社区传播。
3. **点对点分享**：`ott://` 深链与 repo URL 直接传播，不经过任何目录。

### 8.2 治理章程（三方角色）

| 角色 | 职责 | 明确不做 |
|:---|:---|:---|
| 协议维护者（open-typing-texts 仓） | 维护 spec、schema、兼容测试包 | 不运营目录准入、不托管内容 |
| 客户端（typetype） | 实现协议、提供订阅管理、blocklist 机制 | 不内置源、不审核 repo 内容 |
| Repo 维护者（任意第三方） | 维护清单质量与合规、自负法律责任 | 不分发未经签名门槛的可执行内容；L3 受签名+沙箱约束（ADR-010 决策 3 修订） |

下架机制：客户端内置可更新的 repo blocklist（用户可关闭）+ 用户一键移除/禁用。这与"协议无中心"不矛盾——blocklist 是客户端本地策略，不是协议层强制。

### 8.3 权利声明机读化

`rights_summary`（当前 adapter 硬编码 `"user-provided"`）演进为结构化字段（Core 1.1 候选，向后兼容）：

```json
"rights": { "license": "CC-BY-SA-4.0", "attribution": "...", "commercial_use": false }
```

---

## 9. 协议演进治理

- OTT Core 与 OTT Repo **独立语义化版本**：Core 管数据面，Repo 管控制面，互不阻塞演进。
- 新能力一律走 Optional Profile + `features` 协商（ADR-009 已有先例：range read、Collection 均按此处理）。
- 兼容测试包（canonical fixtures）扩展到 repo manifest：有效/无效 manifest 样例入库，客户端跑跨仓漂移检测（沿用 `test_ott_cross_repo_compatibility.py` 机制）。
- `requires.ott_core` / `requires.client_features` 提供 kazumi API level 式的前向协商：客户端不满足要求时整 repo 标记"不兼容"并说明原因，不做静默降级。

---

## 10. 分阶段路线

每阶段独立交付、向后兼容；前一阶段不阻塞后续协议设计。

| 阶段 | 范围 | 仓 | 协议变更 |
|:---|:---|:---|:---|
| Phase 0 ✓ | OTT Core v1 数据面 | 两仓 | 已完成（ADR-009） |
| Phase 1 ✓ | 客户端多 authority：`SourceReposConfig` + 聚合层 + 订阅管理 UI + 旧配置迁移 | typetype | **零协议变更**（repo 格式先按草案实现） |
| Phase 2 ✓ | OTT Repo v1 定稿：spec、ott-repo.schema.json、fixtures、directory 语义、`authority_id`/`repo_url` 增量字段 | open-typing-texts | 新增独立构件，Core 不动 |
| Phase 3 ✓ | 声明式规则源（L1 `ott_rule_interpreter.py`）+ 脚本源（L3 `ott_script_client.py` + `ott_script_safety.py` + `ott_script_runner.py` 子进程沙箱）、规则/脚本调试工具 | typetype | Repo v1.1 |
| Phase 4（部分 ✓） | 签名信任（TOFU）已落地（Phase 2.3：`trust_state` 门控 L3）；官方默认目录、`ott://` 深链未落地 | 两仓 | Repo v1.2 |
| Phase 5（预留） | 内容寻址分发、range read、Collection、Client SDK | — | 见 §12 |

---

## 11. 场景自检

| 场景 | 本设计的回答 |
|:---|:---|
| 新用户如何获取第一个源 | 三条路径：默认目录里挑（可关）；粘贴 repo URL / 分享串；本机跑 `ott-adapter`（authority `local`，零配置） |
| 第三方如何发布源 | 跑 adapter 或生成 Static Profile 放任意静态托管 → 得到 instance；自建 repo manifest 引用它，或投稿给社区目录维护者 |
| 实例作者如何被发现 | directory 投稿 + `ott://` 深链传播 + `repo_url` 回指（未订阅用户点开分享链接即被引导订阅来源 repo） |
| 进度在多实例间如何隔离 | URN `ott:{authority}:{entry_id}@{revision_id}`；authority 身份规范化（§6.1）防冲突 |
| 恶意 repo 能造成什么损害 | 见 §5.3：无执行面、有 hash 校验、可一键禁用、blocklist 兜底 |

---

## 12. 远期方向（明确不做进 v1）

| 方向 | 预留点 | 为什么现在不做 |
|:---|:---|:---|
| 内容寻址分发（CAS/CDN/P2P） | `content_hash` 已就位；未来可选 `by-hash` 端点与 multihash 前缀 | 需要多实例规模验证需求，YAGNI |
| 任意 range read | ADR-009 已记为 Optional Profile 候选 | Unicode/缓存语义复杂 |
| Collection 对象 | 暂用 `source_key` + tags/category | ADR-009 已推迟 |
| 完整 Revision 历史 | revision 模型已就位 | Core v1 非必需 |
| Client SDK | 协议 + fixtures 已足够第三方实现 | 等第二个客户端出现（ADR-009） |
| 跨客户端生态（非 typetype） | 协议与测试包即生态邀请 | 自然结果，无需投入 |
