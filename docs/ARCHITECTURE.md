# TypeType 架构设计手册
<!-- 状态: active | 最后验证: 2026-08-13 -->

## 📍 文档导航卡（你在这里）

本文档是 **架构事实来源**（代码权威）。出现信息冲突时以本文为准。

| 当前文档 | 其他核心文档 | 快速链接 |
| :--- | :--- | :--- |
| **本文** — 架构分层、数据流、依赖规则、陷阱 | [README.md](../README.md) — 快速入门<br>[AGENTS.md](../AGENTS.md) — 开发规范 | [快速开始](#快速开始)<br>[分层架构](#分层架构)<br>[文本源三层模型](#文本源三层模型)<br>[数据流](#核心数据流)<br>[已知陷阱](#已知陷阱) |

---

> 最后更新：2026-08-13

---

## 快速开始

```bash
# 环境：Python 3.12+, uv 0.9.26+
uv sync
uv run python main.py
```

| 命令 | 说明 |
|:--- |:--- |
| `uv run python main.py` | 启动应用 |
| `uv run pytest` | 运行测试 |
| `uv run ruff check .` | 代码检查 |
| `uv run ruff format --check .` | 格式检查 |
| `TYPETYPE_DEBUG=1 uv run python main.py` | 调试模式 |

### 日志开关

- `TYPETYPE_DEBUG=1` — 开启 debug 日志
- `TYPETYPE_LOG_LEVEL=debug\|info\|warning\|error\|none` — 精确控制

---

## 一句话理解项目

TypeType 是一个 **PySide6 + QML 桌面打字练习应用**：

> **QML 不直接碰业务，Domain 不直接碰 Qt。**

- QML 负责页面与交互
- `Bridge + Adapters` 负责 Qt/QML 适配
- `UseCases + Gateways` 负责编排与边界整合
- `Domain Services` 负责纯业务逻辑
- `Ports + Integration` 负责替换型外部依赖

---

## 分层架构

```text
QML UI
  -> Presentation (Bridge + Adapters)
  -> Application (UseCases + Gateways)
  -> Domain / Ports
  -> Integration / Infrastructure
```

### 各层职责

| 层 | 当前组件 | 职责 |
|:--- |:--- |:---|
| QML | `src/qml/` | 页面、交互、布局、局部 UI 状态 |
| Presentation | `Bridge` | QML 门面：属性代理、信号转发、Slot 入口 |
| Presentation | `*Adapter` | Qt 适配、线程协调、错误回传 |
| Application | `*UseCase` | 流程编排、业务验证 |
| Application | `TypingSessionContext` | 会话状态机：阶段/来源模式/分片载文 |
| Application | `*Gateway` | 来源路由、DTO/剪贴板、异常映射 |
| Domain | `*Service` | 纯业务逻辑、状态管理、统计计算 |
| Ports | 各 Port 协议 | 抽象协议 |
| Integration | 各 Port 实现 | Port 实现 |
| Infrastructure | `ApiClient` / `network_errors` | 通用 HTTP 客户端（晴发文/AI 等第三方服务使用）、网络异常分类 |

---

## 目录结构

### Python 后端

```
src/backend/
├── application/
│   ├── exception_handler.py
│   ├── session_context.py
│   ├── gateways/          # gateway 实现
│   └── usecases/          # usecase
├── config/                # 配置 + 容器工厂
├── domain/services/       # domain service
├── infrastructure/        # HTTP 客户端 + 异常分类
├── integration/           # Port 实现
├── models/
│   ├── dto/               # 数据传输对象
│   └── entity/            # 领域实体
├── ports/                 # 抽象协议
├── presentation/
│   ├── bridge.py          # QML 门面
│   └── adapters/          # adapter
├── security/              # 加密 + 安全存储
├── utils/                 # 日志 + 文本工具
└── workers/               # 后台 worker
```

> 完整文件树见 git 仓库。本文档不再维护逐文件列表（代码提交即变更）。

### 载文入口

| 入口 | 文件 | 触发方式 | 分类 | 分段模式 | 乱序 |
|:--- |:--- |:--- |:--- |:---|:---|
| 剪贴板 | `ToolLine.qml` 按钮 | Ctrl+V | 本地 | ✅ | ✅ |
| 载文中心 | `TextLoadHubPage.qml` | 侧边栏 / F2（自定义） | 本地 + OTT 订阅 | ✅ | ✅ |
| 晴发文 | `TypingPage.qml` Ctrl+R | 快捷键 / 工具栏按钮 | **第三方网络** | **服务端分段** ¹ | ❌ |
| AI 智能推荐 | 设置页 / 工具栏按钮 | 手动触发 | **第三方网络**（LLM 出题） | ❌ | ❌ |

¹ 晴发文不走 App 的分片/乱序机制，文本分段由晴发文服务端提供 (`loadPrevWenlaiSegment` / `loadNextWenlaiSegment`)。

#### 载文分类说明（对应三层模型）

- **第 1 层（本地文件）**：剪贴板、自定义、本地文库、练单器、前/中/后五百、打词必备单字 — 文本来自本地文件或用户输入
- **第 2 层（开源文库 / OTT）**：OTT Core v1 只读分发协议提供的文本（通过 OTT Repo 订阅或内置离线源）— 由 `TextLoadHubPage.qml` 的「开源文库」标签接入
- **第 3 层（即时拉取）**：晴发文 — 文本来自晴跟打作者维护的服务端 (qingfawen.fcxxz.com)；AI 智能推荐 — 文本由 LLM API 按薄弱字生成

#### 分段模式与乱序

除晴发文外，所有载文入口共享同一组分片/乱序组件：
- `SliceSettingsPanel` — 分片大小、起始片、全文乱序
- `SliceCriteriaPanel` — 达标条件（击键/速度/键准/通过次数）、失败后行为

OTT segmented 大文本使用服务端定义的 segment 边界，并通过 `OttSegmentProvider` 接入通用分片管线。为避免客户端拉取完整远程长文，OTT segmented 不启用全文乱序；普通按段推进、随机段、重打仍走统一分片控制。

晴发文单独在服务端做分段，App 侧只做逐段推进。

#### 排行榜与成绩提交

typetype-server 已随 [ADR-013](./decisions/013-converge-to-three-repo-model.md) 移除：客户端不再有服务端排行榜、成绩上传、账号体系与 `text_id` 回查。成绩统计均为本地（字符级 SQLite 统计 + 打字历史），载文来源不再区分排行榜资格。去中心化排行榜按 ADR-012 独立推进，本次未留占位。

---

## 核心数据流

### 文本加载链路

```
ToolLine.qml / TextLoadHubPage.qml
  -> appBridge.requestLoadText(sourceKey) 或联邦载文 Slot
  -> Bridge -> TextAdapter / RegistryAdapter
  -> LoadTextUseCase.plan_load(sourceKey)
  -> TextSourceGateway -> TextLoadPlan
  -> TextLoadWorker（后台线程）
  -> LoadTextUseCase.load(plan)
  -> QtLocalTextLoader（本地文件）/ OttFederationProvider（OTT 联邦，Worker）
  -> Adapter emit textLoaded() -> TypingPage.applyLoadedText()
```

### 打字统计链路

```
QML 输入事件
  -> Bridge -> TypingAdapter
  -> TypingService（计数、速度、错误数）
  -> CharStatsService.accumulate()
  -> flush_async()
  -> SqliteCharStatsRepository.save_batch()
```

### 薄弱字查询链路

```
WeakCharsPage.qml
  -> appBridge.loadWeakChars(n, sortMode, weights)
  -> CharStatsAdapter -> WeakCharsQueryWorker
  -> CharStatsService -> SqliteCharStatsRepository
  -> Adapter emit weakestCharsLoaded -> QML 渲染
```

### OTA 更新链路

```
启动时 main.py -> trigger_auto_update_check()
  -> UpdateAdapter.start_auto_check()（后台 Worker，静默失败）
  -> UpdateChecker.check_for_update()  // GitHub API → 已验签 version.json 降级链
  -> checkFinished(available, version, error) -> QML「关于与更新」区

用户触发 downloadAndInstallUpdate(version)
  -> UpdateAdapter 下载（直链 + update.mirrors 镜像逐个尝试，sha256 校验）
  -> 解压到临时目录 -> resources/updater/* 平台小更新器替换安装目录并重启
```

> **设计要点**：Bridge 不直接依赖 Integration 对象，更新检查/下载均走 `UpdateAdapter` 代理 + Worker。

---

## 依赖规则

### 允许的依赖方向

```text
Bridge -> Adapters
Adapters -> Application
Adapters -> Domain（仅纯业务服务直连）
Application -> Domain / Ports / Config
Integration / Infrastructure -> Ports / Domain
```

### 明确禁止

```text
Presentation -> Integration / Infrastructure
Domain -> Qt / PySide / QML
UseCase -> Qt 类型
Adapter 做业务来源路由
```

### RuntimeConfig 的边界

| 用法 | 是否允许 |
|:--- |:--- |
| `TextSourceGateway` 持有并做来源路由 | ✅ |
| `TextAdapter` 持有并做 UI 展示 | ✅ |
| `TextAdapter` 依据配置做业务决策 | ❌ |
| Bridge 直接依赖 RuntimeConfig | ❌ |
| Bridge 直接持有 Integration 对象 | ❌ |

---

## 修改一个功能时怎么判断改哪里

| 场景 | 通常改 |
|:--- |:--- |
| 新增本地文本来源 | `config.json` `text_sources` 加条目（`{label, local_path}`），零代码 |
| 新增远程文本源 | 订阅 OTT Repo 源仓库（`source_repos`），或新增独立 Provider 栈（参考晴发文） |
| 新增统计规则 | `TypingService` / `CharStatsService` → entity/DTO → 测试 |
| 新增 QML 能力 | QML 页面 → `Bridge` → 对应 `Adapter` → 必要时加 worker |
| 新增跨组件业务流程 | `application/usecases/` → gateway/port → adapter 调用 |

---

## 已知陷阱（架构设计类）

> **分类说明**：编码实践类陷阱见 [AGENTS.md § 已知陷阱](../AGENTS.md#8-已知陷阱)。

### 误区 1：所有业务都必须经过 UseCase

不是。**有编排价值 → UseCase**，**单服务调用 → Adapter 直连 Domain Service**。强行包一层纯转发 UseCase 只会增加间接层。

### 误区 2：`TextAdapter` 持有 `RuntimeConfig` 等于做业务路由

不是。它目前只做来源列表展示和默认来源展示。业务路由在 `TextSourceGateway`。

### 误区 3：Domain 不能依赖 Repository 协议

Domain 可以依赖 **抽象协议（Port）**，不能依赖 **具体实现（SQLite / HTTP / Qt）**。

### 误区 4：QML 不允许指定任何字体

普通 UI 字体由 `main.py` 统一设置；但 `TypingPage.qml` 对正文使用了专用阅读字体，这是当前实现。

### StackView 生命周期时序陷阱

`Connections.enabled: StackView.status === StackView.Active` 守卫时，`StackView.onActivating` 发出的信号会被丢弃。必须用：

```
onActivating → 只做状态重置
onActivated → Qt.callLater() 延迟触发信号
```

相关决策见 [ADR-003：单实例页面导航](./decisions/003-single-instance-page-navigation.md)。

---

## 文本源三层模型

> 决策依据：ADR-008（`docs/decisions/008-text-source-three-layer-model.md`）。
> 按「数据如何到达客户端」划分三层，不强行统一。
>
> **命名约定**：第 2 层的用户-facing 名称是**开源文库**；标准边界是 OTT Core v1。`/ott/v1` 是协议路径版本，OTT adapter 当前包版本是独立的 `0.5.0`；不要把旧 adapter 文案中的 “v2” 当成协议版本。实现类型为 `OttFederationProvider`（多 repo 联邦聚合）+ `OttClient`。旧的 `OttTextProvider` / `RegistryTextProvider` / `registry.primary_url` / `Loader` / `LeaderboardMode` 已随 ADR-013 移除，OTT 统一走 `source_repos` 订阅。

### 三层职责对照

| 维度 | 第 1 层：本地文件 | 第 2 层：开源文库 | 第 3 层：即时拉取 |
|:---|:---|:---|:---|
| **数据来源** | 用户/打包 txt | OTT Repo 订阅源仓库 | 第三方实时 API / LLM |
| **时效性** | 静态 | 日级/周级延迟可接受 | 秒级，用户实时交互 |
| **网络韧性要求** | 无 | 低（离线读缓存兜底）| 高（实时）|
| **客户端缓存** | 不需要 | **必须**（TTL + stale-while-revalidate） | 不需要 |
| **账号要求** | 无 | 无 | 晴发文有（token_store）；AI 有（keyring）|
| **现配实现** | ✅ `QtLocalTextLoader` | ✅ `OttFederationProvider` + `OttSegmentProvider` | ✅ 晴发文 / AI 智能推荐独立 Pipeline |
| **配置入口** | `config.json` `text_sources` | `config.json` `source_repos` | 独立配置段 / 设置页 |

### 文本源扩展路径

| 想加什么 | 走哪层 | 改动量 |
|:---|:---|:---|
| 新本地练习文件 | 第 1 层 | `config.json` `text_sources` 加 1 行（`{label, local_path}`），零代码 |
| 静态文集（每日一文、古诗文等）| 第 2 层 | OTT 仓库加脚本或导入内容；typetype 通过 `/ott/v1` 读取 |
| 第三方带认证实时源 | 第 3 层 | 完整 Port + Gateway + UseCase + Adapter（参考晴发文）|

### v2 来源模型（ADR-013 收敛后）

- `Loader` 收敛为仅 `LOCAL_FILE`，`LeaderboardMode` 枚举整体删除，`TextSourceEntry` 简化为 `{key, label, local_path}`（均为本地文件）。
- OTT 订阅不再进 `text_sources`：源仓库条目统一在 `source_repos` 订阅，由 `RegistryAdapter`（Worker 异步）聚合到载文中心「开源文库」标签。
- 晴发文 / AI 智能推荐保持独立 Pipeline，不经过 `TextSourceGateway` 路由。

### 晴发文特殊地位

晴发文独立于 `TextSourceConfig.sources`（拥有自己的 Port / Gateway / UseCase / Adapter），
不走 `TextSourceGateway` 路由。它是第 3 层（即时拉取）的参照实现，保持不动。

```
         TextSourceConfig.sources（v2：仅本地文件）
                   │
                   ▼
                 第1层
               本地文件
         (QtLocalTextLoader)

         OttFederationProvider（第 2 层，走 source_repos 订阅）
                   │
                   ▼
                 开源文库
         (ott-instance / ott-rule / ott-script)

                    ┌────── 晴发文独立 Pipeline ──────┐
                    │  WenlaiProvider → WenlaiGateway │
                    │  → LoadWenlaiTextUseCase        │
                    │  → WenlaiAdapter               │
                    └────────────────────────────────┘

                    ┌────── AI 智能推荐独立 Pipeline ──┐
                    │  LlmTextProvider → AiGateway    │
                    │  → AiTextAdapter                │
                    └────────────────────────────────┘
```

### 开源文库缓存层

内部实现为 `OttFederationProvider`（多 repo 联邦）+ `OttClient`。标准路径按 `/ott/v1` Service Profile → Static Profile (`/ott.json`、`/sources.json`、`/entries.json` 等) 的顺序读取；manifest `endpoints[].profile` 显式声明 `service`/`static` 时，客户端尊重声明、只探测对应 profile（如内置 `file://` 静态源不再无谓打 service 路径）；adapter-private `/api/entries` 不作为 typetype 客户端依赖面。

缓存层决策树（`RepoManifestCache` / 条目缓存）：

```
fetch_text_by_key(key)
  ├─ cache_hit + 未过期 → 返回缓存
  ├─ cache_hit + 过期 → 返回 stale + 后台刷新（stale-while-revalidate）
  ├─ cache miss + 在线 → 请求订阅源仓库 URL，成功写缓存
  └─ cache miss + 离线 → 返回 stale（无视 TTL 兜底）
```

### 动态源快照目录（Content Snapshot + Freshness）

- `EntrySnapshotStore`（integration）：`registry_cache_dir()/snapshots/{authority_hash}/{entry_id}.json`，列表物化内容落盘，原子写，保留最近 N 条
- `RefreshPolicy`：static / interval / on_demand 三模式；用户覆盖（`config.source_refresh_overrides`）> manifest 声明（未来）> 推断（instance→static、rule/script/bridge→on_demand）
- `SnapshotCatalogService`（application）：物化→写快照→prune；`load_entry` 快照优先（不重抽）；`scheduled_tick` 仅刷新 interval 到期源
- `RefreshScheduler`：QTimer 60s tick，Qt 环境可用，非 Qt 降级手动

## OTT Repo 控制面（Phase 1-3，多 authority 联邦聚合 + 规则/脚本源）

> 决策依据：ADR-010（`docs/decisions/010-decentralized-source-ecosystem.md`），设计文档 `docs/designs/decentralized-source-ecosystem.md`。
> OTT Core v1 **数据面不变**；本节是独立的 **OTT Repo 控制面**（订阅、信任、发现），按 Phase 1「零协议变更」落地。

### 架构定位

```
Directory（可选，发现层）                ← 未来 Phase 2+
  └─ Repo（源仓库 / 订阅）               ← 控制面核心（本节）
       └─ Instance / Rule / Bridge（源）
            └─ Entry / Segment          ← OTT Core v1 数据面（不变）
```

| 组件 | 位置 | 职责 |
|:---|:---|:---|
| `SourceRepoEntry` / `SourceReposConfig` | `runtime_config.py` | 订阅列表数据模型（v2：纯订阅，`registry.primary_url` 已删除） |
| `RepoManifestCache` | `integration/ott_repo_manifest.py` | 单订阅 manifest 拉取与缓存（TTL/stale/原子写/后台刷新） |
| `validate_repo_manifest()` | `integration/ott_repo_manifest.py` | manifest 校验与归一化（遵循 OTT Repo v1 草案） |
| `OttFederationProvider` | `integration/ott_federation_provider.py` | 多 repo 联邦聚合（ott-instance + ott-rule）、authority 命名空间隔离、priority + 健康度 failover |
| `_RuleClient` | `integration/ott_federation_provider.py` | ott-rule 客户端封装，调用 L1 解释器执行声明式规则 |
| `OttRuleInterpreter` | `integration/ott_rule_interpreter.py` | L1 声明式规则解释器（JSON path / 正则 / CSS 选择器 + transform 管道） |
| `_ScriptClient` | `integration/ott_federation_provider.py` | ott-script 客户端封装（下载 + AST 检查 + 沙箱执行） |
| `ScriptSandbox` | `integration/ott_script_client.py` | ott-script 沙箱调度（写临时文件 + 启动子进程 + 解析结果） |
| `ScriptCache` | `integration/ott_script_client.py` | 脚本下载缓存（TTL + AST 校验 + 原子写 + 离线回退） |
| `ott_script_runner.py` | `integration/ott_script_runner.py` | 子进程沙箱入口（资源限制 + 受限 builtins + 白名单模块 + stdout JSON） |
| `validate_script_source()` | `integration/ott_script_safety.py` | 脚本 AST 安全检查（黑名单 import/call + 动态导入检测） |
| `SmartRouteSelector` | `integration/smart_router.py` | 网络选路：按实时延迟/连通性在原始地址、jsDelivr、`ott.route_mirrors` 前缀镜像、manifest mirrors 间选路（短超时并发探测 + TTL 缓存 + 失败冷却 + 真实请求回写；供 `RepoManifestCache`/`OttCachedFetcher`/`ScriptCache` 复用） |
| `EntrySnapshotStore` | `integration/entry_snapshot_store.py` | 条目内容快照落盘（`captured_at`=内容变化时间 + `last_checked_at`=检查时间，原子写） |
| `SourceStatusStore` | `integration/source_status_store.py` | per-authority 源健康状态持久化（last check/success/error + 连续失败计数） |
| `SnapshotCatalogService` | `application/services/snapshot_catalog_service.py` | 物化 → 快照/prune → 刷新策略/源状态 → 列表装饰 |
| `RegistryAdapter` | `presentation/adapters/registry_adapter.py` | 订阅管理 + 条目聚合 + 源级刷新/健康状态的 Qt 适配层（Worker 异步） |
| `RepoEntriesPanel` | `components/RepoEntriesPanel.qml` | 载文中心「开源文库」标签的联邦条目列表面板（源组卡片 + 选中即载入） |
| `RepoConfigDialog` | `components/RepoConfigDialog.qml` | 订阅源管理弹窗（启用/信任/删除 + 元数据/不兼容原因） |
| `SourceInfoDialog` | `components/SourceInfoDialog.qml` | 源详情弹窗（tier/健康/刷新频率覆盖） |

### 订阅数据流

```
config.json.source_repos[]
  │
  ├─ RepoManifestCache.get_manifest(repo)
  │     ├─ cache hit fresh → 返回
  │     ├─ cache hit stale → 返回缓存 + 后台刷新
  │     └─ miss → HTTP GET url → validate → 原子写
  │
  └─ OttFederationProvider.list_all_entries()
        └─ 遍历 enabled repos → manifest.sources[type=ott-instance]
              └─ 每 authority 建 _InstanceClient（OttClient × endpoints）
                    └─ priority 排序 + 健康度指数退避 failover
                          └─ 合并条目（authority 命名空间去重）
```

### 四级信任模型（客户端强制）

| 级 | 形态 | 执行面 | 分发方式 |
|:---|:---|:---|:---|
| L0 | OTT 数据实例 | 零执行 | 订阅即用 |
| L1 | 声明式规则源（ott-rule） | 受限解释器 | 已落地 |
| L2 | 桥接源（ott-bridge，即时 API） | 协议化 adapter，凭据本地 | 未落地（控制面解析；provider 未实现，订阅面板显示"暂不支持"） |
| L3 | 抓取脚本（ott-script） | 子进程沙箱（AST 白名单 + 资源限制 + 进程隔离） | 已落地，可经 Repo 分发 |

不变式：客户端从网络订阅的 L0/L1/L2 内容无任意代码执行面；L3 脚本在子进程沙箱内执行，逃逸不突破进程边界。

### 目录结构（新增文件）

```
src/backend/config/runtime_config.py        # + SourceRepoEntry, SourceReposConfig, _parse_source_repos, 迁移逻辑
src/backend/integration/
  ├─ ott_repo_manifest.py                   # RepoManifestCache + validate_repo_manifest
  ├─ ott_federation_provider.py             # OttFederationProvider + _InstanceClient + _RuleClient + _ScriptClient
  ├─ ott_rule_interpreter.py                # OttRuleInterpreter（L1 声明式规则解释器）
  ├─ ott_script_client.py                   # ScriptSandbox + ScriptCache（L3 脚本源调度）
  ├─ ott_script_safety.py                   # validate_script_source（AST 安全检查）
  ├─ ott_script_runner.py                   # 子进程沙箱入口（资源限制 + 执行 + stdout JSON）
  └─ smart_router.py                        # SmartRouteSelector（按实时延迟/连通性在 CDN/镜像/代理前缀间选路）
src/backend/presentation/adapters/
  └─ registry_adapter.py                    # RegistryAdapter（Qt 适配层）
src/backend/config/container.py             # + manifest_cache, federation, registry_adapter
src/qml/components/ReposManagementPanel.qml # 源仓库管理面板（独立页面承载）
src/qml/components/RepoEntriesPanel.qml      # 开源文库条目列表面板
src/qml/components/WenlaiSourcePanel.qml     # 晴发文即时源面板
src/qml/components/AiSourcePanel.qml         # AI 推荐即时源面板
src/qml/helpers/TextSourceBehaviors.js      # + repos 来源分派
src/qml/pages/TextLoadHubPage.qml           # 6 来源 tab（本地/开源/练单/晴发文/AI/自定义）+ Segmented 切换
src/qml/pages/ReposManagementPage.qml       # 订阅管理独立子页面
```

### 配置字段

见 [config.md](reference/config.md)（v2 schema：`schema_version=2`，`ott` / `update` / `source_repos` 等顶级段）。订阅列表 `source_repos` 的字段见 `source_repos` 子字段表。

### 客户端约束

- 订阅 manifest 拉取与联邦聚合均走 Worker（不阻塞 UI）
- 离线时返回缓存 manifest（无视 TTL 兜底）
- 签名（裸 Ed25519，minisign 已移除）+ TOFU 已实现（ADR-011 Phase 2.3）：`trust_state` 门控 L3 执行，签名是 L3 的执行门槛而非徽章；L0/L1/L2 签名仍仅作信任信号；验签与 snapshot 链以**网络原始字节**为口径（归一化重构会改变 canonical 字节）；先验签后落盘——pending（首次/公钥变更/撤销）期间拒绝替换缓存，TOFU 未确认内容不服务；revocations 仅签名验证通过的 manifest 应用
- authority 冲突时按 repo 分组并列展示，由用户选择

### L1 规则（ott-rule）URL 约束

- 仅接受公网 `http://` / `https://`；`file:`、环回、私有/保留地址（含编码、进制数值 IP、IPv4 映射 IPv6、link-local）一律拒绝
- 非 80/443 端口、DNS 解析失败（离线/内网解析）拒绝——规则源必须解析到公网 IP 才能请求
- HTTP 请求做 DNS pin（IP 直连 + 原 Host 头）；HTTPS 不 pin（TLS 证书按域名校验，内网 IP 无合法证书，天然防 rebinding）
- 全部请求显式 `follow_redirects=False`（4 处 httpx.Client）

### L1 规则 schema v2（Phase 1.3）

规则可选用 v2 字段（设计见 `docs/designs/ott-dsl.md`）：

- `steps`：DSL 顺序管道（`ott_dsl.py` 45 原语白名单求值器），前步输出作为后步首参，`{"ref": "body"}` 引用 `request.body` 字面量；末步输出作为 POST 请求体
- `request.body`：无 `steps` 时为字面量；有 `steps` 时经管道构造。body 类型规范化：str/bytes 直传、dict/list → JSON 序列化、int/bool 字符串化、其余类型规则拒绝
- `permissions.network`：域名白名单（子域匹配），**声明时生效**——URL 不在白名单内 → 整条规则拒绝；未声明回退 `validate_url` 基线
- `rights.min_api_level`：客户端 API level（`OttRuleInterpreter(api_level=...)`，生产经 `CLIENT_API_LEVEL`）低于声明值 → 规则标记不兼容跳过
- `request.headers`：`Content-Type` 等 HTTP 头必须由规则显式声明（`httpx content=` 不自动添加 JSON 头）
- 校验拒绝：`transform` 与 `steps` 并存、未知原语、steps 超限（`MAX_STEPS`/`MAX_CALLS`/1MB 值）→ 整条规则跳过
- 引擎约束：单值 ≤1MB、深度 ≤32、调用 ≤1000、步数 ≤8、步间数据 ≤2MB；正则原语复用 0.B1 子进程方案

---

## OTA 更新（ADR-014）

> 决策依据：ADR-014（`docs/decisions/014-ota-update-check-and-mirror-download.md`）。

### 架构定位

| 组件 | 位置 | 职责 |
|:---|:---|:---|
| `APP_VERSION` | `src/backend/version.py` | 运行时版本单一事实源（Nuitka 产物内不可读 pyproject.toml） |
| `UpdateChecker` | `integration/update_checker.py` | GitHub API → 已验签 `version.json` 降级链 + 镜像下载 + sha256 校验 |
| `UpdateWorker` | `workers/update_worker.py` | 后台异步检查（节流 + 静默失败） |
| `UpdateAdapter` | `presentation/adapters/update_adapter.py` | 平台资产匹配、下载解压、调用 updater 脚本；Bridge 信号代理 |
| `updater.sh` / `updater.bat` | `resources/updater/` | 平台替换/重启小工具 |
| `scripts/gen_version_manifest.py` | `scripts/` | CI 生成并签名 `version.json`（tag / assets / sha256 / Ed25519） |
| `build-release.yml` `assert-version` | `.github/workflows/` | 发布 tag / pyproject / `APP_VERSION` 一致性断言 |

### 配置字段

`update` 段：`enabled` / `auto_check` / `check_interval_hours` / `channel` / `mirrors`（详见 [config.md](reference/config.md)）。

### 客户端约束

- 更新检查/下载均走 Worker（不阻塞 UI）；自动检查失败静默
- 下载按「直链 + `update.mirrors` 镜像」逐个尝试，**每个下载必须 sha256 校验**，失败立即丢弃换下一个源
- 安装用原子目录切换（新目录就绪 → 改名切换 → 失败回滚保留旧目录）；每次全量归档，不做差分更新

---

## 后续方向

| 优先级 | 方向 |
|:--- |:---|
| 高 | 基于薄弱字自动生成练习材料 |
| 中 | 远端同步字符统计 / AI Typing Coach |
| 低 | 更细粒度学习分析 |

---

## RinUI 本地修改概要

RinUI 是 vendored 第三方框架。必要的修改记录在 `RinUI/LOCAL_MODIFICATIONS.md`。

当前已记录的修改：
1. `ContextMenu.qml` — 下拉弹出位置修复 + height 动画修复
2. `NavigationBar.qml` — Back 按钮水平对齐
3. `NavigationView.qml` — StackView 重构为单实例
4. `FluentPage.qml` — 移除 OpacityMask（GPU 阻塞）+ anchors 替换为 x/y

---

## 当前限制

客户端暂无防作弊措施。联网内容（OTT 订阅、规则/脚本源）以来源自身可信度为准；晴发文/AI 为第三方即时服务，受第三方可用性与账号限制影响。
