# ADR-009: OTT Core v1 与 typetype 客户端演进

<!-- 状态: accepted | 决策日期: 2026-07-09 | 最后验证: 2026-07-10 -->

> 本 ADR 是 ADR-008 的后续修订。核心结论：**OTT 是标准协议与参考实现，typetype 是 OTT 客户端之一**。typetype 应适配 OTT 标准，而不是让 OTT 为 typetype 当前实现让步。

## 背景

`open-typing-texts` 已经从“托管文本内容的仓库”演进为“开源打字文本源标准 + 本地适配器”：

- 仓库不提供、不托管任何文本内容，只提供抓取脚本模板和本地适配器。
- 用户运行 `ott-adapter` 后，本地暴露 `http://127.0.0.1:18888`。
- typetype 当前通过 `registry.primary_url` 读取该本地服务。

这暴露出一个标准化问题：当前 typetype 已经依赖 OTT 适配器的 `/api/entries`，但 OTT README / SPEC 公开稳定面仍主要是 `/registry_index.json` 和 `/content/{source_key}.json`。同时，`/api/entries` 是条目分页，不是单篇大文本分块；它默认仍可返回完整正文。

本 ADR 的目标不是让 OTT 贴合 typetype 现状，而是定义一套可被 typetype、其他打字客户端、静态文件服务、本地适配器共同实现的 OTT 协议边界。

版本命名约定：

| 名称 | 当前值 | 含义 |
|:---|:---|:---|
| OTT Core | `1.0` | 数据模型与只读分发协议版本 |
| Service Profile 路径 | `/ott/v1` | Core v1 的 HTTP 命名空间 |
| OTT adapter 包版本 | `0.5.0` | 参考实现发布版本 |
| 旧索引 schema | `registry_index.json version: 2` | 历史兼容索引，不是 OTT Core 版本 |

因此当前不是“OTT v2”；“v2”只应出现在旧索引 schema 或历史 adapter 文案中。

## 问题判断

### 1. 标准核心与参考实现混在一起

OTT 需要覆盖抓取、存储、分发和客户端接入，但这些能力不应都进入 Core 标准。

| 层 | 是否进入 Core v1 | 说明 |
|:---|:---:|:---|
| 文本身份与元数据 | ✅ | 所有客户端必须理解 |
| 只读分发 API / 文件布局 | ✅ | typetype 等客户端依赖 |
| 大小文本统一读取模型 | ✅ | 大文本不能继续全量正文分发 |
| 抓取脚本 | ❌ | 参考实现能力，不应成为客户端协议 |
| 本地存储引擎 | ❌ | 文件系统、SQLite、CAS 都可实现 |
| 管理 API / Web UI | ❌ | 适配器私有能力，应与只读分发隔离 |
| Client SDK | ❌ | 后续工具，先冻结协议和兼容测试 |

### 2. 当前 `/api` 不能直接升格为标准

当前 `ott_adapter/server.py` 的 `/api` 同时包含只读分发、脚本运行、脚本保存、删除、调度等管理能力。它适合作为现有适配器实现面，但不适合作为标准客户端依赖面。

标准应新增只读命名空间：

```http
/ott/v1/...
```

管理能力应独立到：

```http
/ott-admin/v1/...
```

typetype 只依赖 `/ott/v1`。`/api` 作为 legacy / adapter-private 兼容层保留，不再扩展为长期协议。

### 3. 大文本不能继续走全量分发

当前 OTT 具备“多条目分页”，但没有真正的“单篇大文本分段读取”：

| 能力 | 当前状态 | 判断 |
|:---|:---:|:---|
| `registry_index.json` 来源索引 | ✅ | Static v1 可继续兼容 |
| `entries[]` 历史条目 | ✅ | 可作为 Entry 模型来源 |
| `/api/entries?page=&limit=` | ✅ | 只是条目分页 |
| 列表摘要不含正文 | ⚠️ | 目标应为默认行为 |
| 按 entry 获取正文详情 | ⚠️ | 需要标准化 |
| 单篇正文分段读取 | ❌ | Core v1 必须补 |

因此，OTT 若要成为大小文本均适配的标准协议，必须把“大文本分段读取”放进 Core 只读分发模型。

## 决策

### 1. OTT Core v1 只定义数据模型与只读分发

Core v1 强制定义四类对象：

| 对象 | 作用 |
|:---|:---|
| `Source` | 文本来源，如 `poem` / `jisubei` / `daily` |
| `EntrySummary` | 列表项摘要，不含完整正文 |
| `EntryDetail` | 单篇文本详情，声明 inline 或 segmented |
| `Segment` | 大文本分段内容 |

`Revision` 作为字段进入 Core v1，但完整修订历史不作为必需能力。Core v1 只要求客户端能识别 `current_revision_id`。

### 2. Fetch / Store / Admin 均为 Profile 或参考实现

OTT 可以提供官方参考实现，但标准不要强制实现细节。

```
OTT Standard
  ├─ Core v1                 数据模型
  ├─ Distribution Profile    只读分发
  │   ├─ Static Profile      静态文件
  │   └─ Service Profile     HTTP 服务
  └─ Optional Profiles
      ├─ Fetch Profile       抓取脚本约定
      ├─ Store Profile       本地存储建议
      └─ Admin Profile       管理 API / Web UI
```

这能保证 typetype 只依赖稳定的只读协议，不关心文本是抓取来的、导入来的、手写的，还是由其他工具生成的。

### 3. Entry 身份与 Revision 分离

`entry_id` 不能用 `source_key + fetched_at` 作为长期协议核心，也不能简单等同于正文 hash。

Core v1 定义：

| 字段 | 含义 | 稳定性 |
|:---|:---|:---|
| `entry_id` | 文本实体身份，同一作品/条目保持稳定 | 稳定 |
| `current_revision_id` | 当前内容版本 | 随内容版本变化 |
| `content_hash` | 当前正文校验 hash | 随正文变化 |
| `source_key` | 所属来源 | 稳定或随迁移变化 |

推荐 typetype 进度键：

```text
ott:{authority}:{entry_id}@{revision_id}
```

这样同一作品修订后可以明确区分进度；同一修订可稳定缓存和续练。

### 4. Core v1 只保留 server-defined segments，不把 range 作为核心

Core v1 的大文本读取模型使用服务端定义的 segment：

```http
GET /ott/v1/entries/{entry_id}/revisions/{revision_id}/segments/{index}
```

不把任意 `range?offset=&length=` 放入 Core v1。

理由：

- typetype 分片练习天然按片段索引工作。
- segment 缓存键稳定，便于离线与续练。
- 任意 range 必须定义字节、Unicode 码点、字素簇、换行归一化等细节，Core v1 不应承担这部分复杂度。

`range` 可以作为未来 Optional Profile。

### 5. typetype 启动方式必须从 Entry 能力派生

typetype 当前把 `registry` 来源固定为 `materialized_text`。这不适合 OTT，因为同一个来源下可能同时有短文和长文。

目标规则：

| `EntryDetail.content_mode` | typetype launch |
|:---|:---|
| `inline` | `materialized_text` |
| `segmented` | `segmented_source` |

因此 launchKind 应从 entry 级 `content_mode` 派生，而不是从 source 级来源类型派生。

## Core v1 数据模型

### Source

```jsonc
{
  "source_key": "poem",
  "label": "诗句",
  "description": "用户本地生成的诗句来源",
  "tags": ["poem"],
  "rights_summary": "user-provided"
}
```

### EntrySummary

列表 API 只返回摘要，不返回完整正文。

```jsonc
{
  "entry_id": "ent_01JZ...",
  "source_key": "poem",
  "title": "标题",
  "preview": "前 100 字左右的预览",
  "char_count": 1200,
  "content_mode": "inline",
  "current_revision_id": "rev_01JZ...",
  "updated_at": "2026-07-09T10:00:00+08:00",
  "tags": ["诗句"]
}
```

### EntryDetail

短文本：

```jsonc
{
  "entry_id": "ent_01JZ...",
  "source_key": "poem",
  "title": "短文标题",
  "content_mode": "inline",
  "char_count": 420,
  "current_revision_id": "rev_01JZ...",
  "content_hash": "sha256:...",
  "content": "完整正文"
}
```

长文本：

```jsonc
{
  "entry_id": "ent_01JZ...",
  "source_key": "novel",
  "title": "长文标题",
  "content_mode": "segmented",
  "char_count": 180000,
  "current_revision_id": "rev_01JZ...",
  "content_hash": "sha256:...",
  "segment_count": 180,
  "segment_size_hint": 1000
}
```

`segment_size_hint` 只是提示值。客户端不得用它自行切原文来替代服务端 segment；真正边界以 `Segment.start_char` / `Segment.end_char` 为准。

### Segment

```jsonc
{
  "entry_id": "ent_01JZ...",
  "revision_id": "rev_01JZ...",
  "index": 1,
  "start_char": 0,
  "end_char": 1000,
  "char_count": 1000,
  "content_hash": "sha256:...",
  "content": "本段正文"
}
```

字符计数沿用 OTT 既有约定：面向打字练习的字符数，不是字节数。分段边界由 OTT 生成方负责，客户端只消费结果。

## Distribution Profile

### Service Profile

只读 HTTP API：

```http
GET /ott/v1/capabilities
GET /ott/v1/sources
GET /ott/v1/entries?source_key=&page=&limit=&q=
GET /ott/v1/entries/{entry_id}
GET /ott/v1/entries/{entry_id}/revisions/{revision_id}/segments/{index}
```

能力发现示例：

```jsonc
{
  "protocol": "ott",
  "version": "1.0",
  "profiles": ["service"],
  "features": {
    "entry_summary": true,
    "inline_content": true,
    "segmented_content": true,
    "search": true,
    "static_fallback": false
  }
}
```

### Static Profile

静态文件布局：

```text
/ott.json
/sources.json
/entries.json
/entries/{entry_id}.json
/segments/{revision_id}/{index}.txt
```

`/ott.json` 是静态能力声明，`/entries.json` 是 `EntrySummary` 发现清单，`/entries/{entry_id}.json` 返回 `EntryDetail`。如果 `content_mode=segmented`，客户端按 `segments/{revision_id}/{index}.txt` 读取分段正文。

Static Profile 允许 GitHub Pages、nginx、本地文件服务等只读托管方式存在，但不要求任何抓取或管理能力。

## typetype 演进

### 目标客户端边界

新增标准客户端抽象：

```text
OttClient
  list_sources()
  list_entries(source_key, page, limit, query)
  get_entry(entry_id)
  get_segment(entry_id, revision_id, index)
```

`OttTextProvider` 承担缓存与 legacy fallback；旧 `RegistryTextProvider` 模块只保留导入兼容。

### 载文入口演进

当前：

```text
source=registry -> materialized_text
```

目标：

```text
entry.content_mode=inline
  -> materialized_text

entry.content_mode=segmented
  -> segmented_source
  -> generic TextSegmentProvider
```

typetype 已有 `TextSegmentProvider`、本地文库 segment、练单器 segment 等基础机制。OTT 大文本不应另建特殊打字流程，而应实现一个 `OttSegmentProvider` 或等价 Adapter 接入通用分段管线。

### 进度与缓存

typetype 的 OTT 进度键使用：

```text
ott:{authority}:{entry_id}@{revision_id}
```

缓存粒度：

| 数据 | 缓存键 |
|:---|:---|
| capabilities | `authority/capabilities` |
| sources | `authority/sources` |
| entry summaries | `authority/entries/query-hash/page` |
| entry detail | `authority/entry/{entry_id}` |
| segment | `authority/entry/{entry_id}/revision/{revision_id}/segment/{index}` |

所有只读分发缓存都应支持 TTL + stale fallback。管理 API 不进入 typetype 缓存模型。

## 分阶段路线

### Phase 0：冻结标准草案

- 在 OTT 仓库新增 `OTT_SPEC.md`，定义 Core v1、Service Profile、Static Profile。
- 将当前 `/api` 标记为 legacy / adapter-private。
- 补 JSON Schema 和兼容测试样例。

### Phase 1：OTT 只读分发面

- 新增 `/ott/v1/capabilities`。
- 新增 summary-only `/ott/v1/entries`。
- 新增 `/ott/v1/entries/{entry_id}`。
- 为现有 `entries[]` 生成稳定 `entry_id`、`current_revision_id`、`content_hash`。

### Phase 2：OTT 大文本分段

- Store 参考实现生成 `Segment` 文件或记录。
- Service Profile 暴露 segment API。
- Static Profile 产出 `/segments/{revision_id}/{index}.txt`。
- 当前完整 `content` 字段继续兼容小文本；长文本不强制内联。

### Phase 3：typetype 标准客户端

- 新增 `OttClient` / `OttTextProvider`。
- `loadRegistryEntries()` 迁移到 summary list。
- 选择条目后按 `EntryDetail.content_mode` 决定 launchKind。
- `OttTextProvider` 保留 legacy fallback；旧 `RegistryTextProvider` 仅作为导入兼容别名。

### Phase 4：typetype 大文本接入

- 增加 `OttSegmentProvider` 或等价实现。
- 将 OTT segmented entry 接入现有 `segmented_source`。
- 进度键迁移到 `ott:{authority}:{entry_id}@{revision_id}`。
- UI 显示 OTT 服务健康、缓存状态、条目模式（短文/长文）。

## 当前实施状态

截至 2026-07-12 已完成：

- OTT 仓库新增 `OTT_SPEC.md`，并实现 `/ott/v1/capabilities`、`/ott/v1/sources`、summary-only `/ott/v1/entries`、entry detail、segment endpoint。
- OTT 列表摘要由索引中的 `ott_entries` 提供；segmented detail 默认不返回全文；`/api` 仍保留为 adapter-private / legacy。
- typetype 的开源文库列表改为优先使用 `/ott/v1/entries`，不再把 `/api/entries` 作为标准 fallback。
- typetype inline OTT 条目通过显式 `loadOttEntry(entry_id)` 加载；segmented OTT 条目通过 `OttSegmentProvider` 接入通用分片管线。
- typetype OTT 续练 key 改为 `ott:{authority}:{entry_id}@{revision_id}`。
- OTT adapter 生成 Static Profile：`/ott.json`、`/sources.json`、`/entries.json`、`/entries/{entry_id}.json`、`/segments/{revision_id}/{index}.txt`。
- typetype 新增 `OttClient`，按 Service Profile → Static Profile → legacy static registry/content 的顺序读取。
- typetype 正式实现迁移为 `OttTextProvider`；`registry` 配置键与 Loader 值继续兼容，旧 provider 模块只做导入转发。
- OTT adapter 新增 `/ott-admin/v1` Admin Profile，Web UI 已迁到该前缀；旧 `/api` 仅作为 legacy 兼容别名保留。

仍未完成：

- JSON Schema 与跨实现兼容测试样例。

## 删除或降级的设计

| 原设计 | 处理 | 原因 |
|:---|:---|:---|
| Core 标准包含 Fetch / Store / Admin / Web UI | 删除 | 这些是参考实现或可选 profile |
| 当前 `/api/entries` 作为长期协议核心 | 删除 | 它是 legacy adapter API，且默认可能返回全文 |
| Core v1 支持任意 `range` | 降级 | Unicode 和缓存语义复杂，先用 server-defined segment |
| Core v1 引入 `Collection` | 降级 | 先用 `source_key` + `tags` / `category` 表达分组 |
| source 级固定 launchKind | 删除 | OTT 同一来源可同时包含 inline 和 segmented entry |
| 强制 CAS / SQLite 存储 | 删除 | 标准要求 hash 和分段结果，不规定存储引擎 |
| 先做 Client SDK | 降级 | 先冻结 JSON Schema、协议文档、兼容测试 |

## 反模式

| 反模式 | 不做原因 |
|:---|:---|
| typetype 执行 OTT 抓取脚本 | RCE 与供应链风险；typetype 只读分发协议 |
| 管理 API 与只读 API 共用客户端依赖面 | 权限边界不清，CORS / CSRF 风险放大 |
| 把列表分页当作大文本分块 | 它只解决条目数量，不解决单篇正文大小 |
| 用标题、全文或抓取时间作为进度身份 | 不稳定，无法表达修订与迁移 |
| 为了“大一统”取消三层模型 | 统一点在 OTT 数据模型和 typetype launch 层，不在抓取/存储实现 |

## 一句话总结

OTT Core v1 应只定义文本身份、修订、摘要、正文详情和分段读取；Fetch、Store、Admin、Web UI 都是可选 Profile 或参考实现。typetype 作为 OTT 客户端实现，只依赖 `/ott/v1` 或 Static Profile，并按 entry 级 `content_mode` 将短文接入 `materialized_text`、长文接入 `segmented_source`。
