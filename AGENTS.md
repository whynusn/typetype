# typetype 项目开发指南
<!-- 状态: active | 最后验证: 2026-07-13 -->

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
| `ARCHITECTURE.md` | 架构事实来源 | 新增/删除文件、架构变更、新架构陷阱 |
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

### 配置系统架构

`config.json` 是唯一的运行时配置文件，位于 `~/.config/typetype/config.json`。

| 文件 | 位置 | 内容 | 写入者 |
|:--- |:--- |:--- |:--- |
| `config.json` | `~/.config/typetype/` | 运行时配置（API 地址、文本源、AI 服务、UI 主题、字体偏好等） | `RuntimeConfig`（主）、`RinUI AppUIConfigManager`（ui 字段） |
| `font_config.json`（已废弃） | `~/.config/typetype/` | 读屏字体路径 | 首次访问时自动迁移到 `config.json.ui.reader_font_path` |

`RuntimeConfig` 设计要点：
- `dataclass` 结构：顶级字段 + 子 Config dataclass（`WenlaiConfig`、`AiConfig`、`RegistryConfig`、`TextSessionConfig`）
- `_from_dict` / `_to_dict`：JSON ↔ dataclass 序列化，`_save_to_file` 以 `_to_dict()` 为基全量写入
- `__post_init__`：**范围校验**（如 `length < 0 → 0`）
- `_safe_int` / `_safe_str`（在 `_from_dict` 中）：**JSON 类型转换**（如字符串 `"bad"` → 默认值 0）
- 写入加 `fcntl.lockf` 文件锁

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
- 所有载文场景统一在 `TextLoadHubPage.qml` 中通过顶部来源切换（`RinUI Segmented`）进入；各来源共享同一组分片/达标组件，不再分散为多个独立入口页

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
3. `container.py` 装配层注入
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

### ⚠️ RuntimeConfig 是 config.json 的唯一序列化者

**问题**：`config.json` 曾被四方无协调写入（RuntimeConfig、RinUI AppUIConfigManager、font_config.json 桥、用户手工编辑），存在 lost-update 风险。

**现状**（2026-07-04 重构后）：
- `RuntimeConfig._save_to_file()` 以 `_to_dict()` 为基全量写入，合并未知字段（前向兼容）
- 写入时加 `fcntl.lockf` 文件锁防止并发冲突
- `ui` 字段已成为 `RuntimeConfig` 的一等公民（`runtime_config.py:148`），通过 `update_ui_config()` 写入
- `font_config.json` 已废弃：`reader_font_path` 改存 `config.json` 的 `ui.reader_font_path`，旧文件在首次访问时自动迁移

**已知限制**：
- `api_timeout` 为启动期常量（`container.py` 创建 `ApiClient` 时使用），运行时不传播变更
- RinUI `AppUIConfigManager` 仍直接读写 config.json 的 `ui` 字段（RinUI 框架内部机制），与 RuntimeConfig 的 `_save_to_file` 存在理论上的并发窗口，但 Python 单线程模型中风险极低

**正确做法**：
- 增加配置字段 → 加在 Config dataclass 上 + `_from_dict` + `_to_dict`，不要绕开 RuntimeConfig
- 修改 UI 配置 → 通过 `runtime_config.update_ui_config(key=value)`，不要直接写文件
- 新子配置 → 遵循 `WenlaiConfig / AiConfig / RegistryConfig` 模式：`@dataclass` + `__post_init__` 范围校验 + `_from_dict` 负责 JSON 类型转换

**历史**：2026-07-04 多相位重构。

### ⚠️ OTT Repo 控制面订阅走 `source_repos`，不走 `registry.primary_url`

**问题**：ADR-0010 落地后，客户端多 authority 订阅统一走 `RuntimeConfig.source_repos`（`SourceReposConfig`）。旧的 `registry.primary_url` / `mirror_url` 仍保留为兼容标识（单实例 OTT 数据面仍可用），但新订阅能力必须写 `source_repos`。

**现状**（Phase 1）：
- `SourceReposConfig` 是一组 `SourceRepoEntry`（url / enabled / trust_state / pinned_pubkey / refresh_ttl_seconds / etag / added_at）
- 旧 `registry.primary_url` 在加载时**自动迁移**为一条等价 `source_repos` 订阅（TTL 沿用 `cache_ttl_seconds`）；已存在 `source_repos` 时不迁移
- 订阅增删改通过 `RuntimeConfig.add_source_repo / remove_source_repo / set_source_repo_enabled / set_source_repo_trust`，不要直接操作 `source_repos.repos` 列表
- manifest 拉取与缓存在 `RepoManifestCache`（TTL/stale-while-revalidate/原子写/后台刷新，复用 OTT Core v1 缓存决策树）
- 联邦聚合在 `OttFederationProvider`：按 authority 命名空间隔离，同 authority 多镜像按 priority + 健康度指数退避 failover

**正确做法**：
- 新增订阅 → `runtime_config.add_source_repo(url)`
- 扩展 manifest 能力 → 改 `validate_repo_manifest()` + `SourceRepoEntry`，遵循 OTT Repo v1 草案
- 消费订阅列表 → 通过 `RegistryAdapter`（Worker 异步），不要在主线程拉取 manifest
- 新子配置字段 → 加在 `SourceRepoEntry` + `_parse_source_repos` + `_to_dict`，保持 RuntimeConfig 为唯一序列化者

**历史**：2026-07-26 Phase 1 落地（ADR-0010）。

### ⚠️ TextSource 使用 Loader + LeaderboardMode 二维正交模型

**问题**：旧的 `SourceType` 枚举（`NETWORK / REGISTRY / LOCAL_RANKED / LOCAL_PRACTICE`）把"加载方式"和"排行榜行为"耦合在单一枚举中，导致 `LOCAL_RANKED` 和 `LOCAL_PRACTICE` 的区别不是本质性的（都是读本地文件），且新增来源类型时必须扩展枚举和 if 分支。

**现状**（2026-07-04 重构后）：
- `TextSourceEntry` 现在由两个正交字段定义：`loader`（决定 Gateway 路由）+ `leaderboard_mode`（决定 text_id 决策）
- `TextSourceEntry.is_local` 属性由 `loader == Loader.LOCAL_FILE` 派生
- `has_ranking` 字段已废弃（从未有独立消费方）
- 旧 `source_type` / `has_ranking` 配置项在加载时自动迁移到新字段

**正确做法**：
- 添加新远程源 → 新增 `Loader` 枚举值 + Gateway 路由分支 + Provider 实现
- 改变排行榜行为 → 设置 `leaderboard_mode`，不影响加载路径
- `text_source_config.py` 是权威定义，`text_source_gateway.py` 和 `load_text_usecase.py` 分别只依赖 `loader` 和 `leaderboard_mode`
- `is_local` 属性由 `TextSourceEntry.is_local` 提供，不要手工判断

**历史**：2026-07-04 重构。

### ⚠️ 开源文库缓存层必须读缓存，禁止直打网络

**问题**：开源文库 provider 的 `_cache_dir` 曾长期只创建不读写，所有请求直打网络，弱网/离线即崩（`cache_ttl_seconds` 是死字段，`cache_dir` 创建但无读写）。

**现状**（Phase 1a/1b 实现后）：
- `OttTextProvider._fetch_json_with_cache()` 实现五层决策树：cache hit → stale-while-revalidate → cache miss → 网络成功写缓存 → 离线兜底
- 基于文件 mtime + `cache_ttl_seconds`（默认 3600s）判断过期
- 原子写：tmp + `Path.replace`，全方法 `try/except OSError` 兜底
- 后台刷新：`QtAsyncExecutor` + `threading.Lock` 去重防重复刷新

**正确做法**：
- 修改 Registry 相关逻辑 → 通过 `_fetch_json_with_cache()` 走缓存层，不要绕过 `_read_cache`/`_write_cache`
- 新增缓存路径 → 复用 `_cache_path(cache_key)` 统一文件布局
- 缓存写入失败/读取失败 → 静默返回 None，不要阻塞主流程

**历史**：2026-07-05 Phase 1a/1b 实现，ADR-008 §决策。

### ⚠️ typetype 只能依赖 OTT 只读协议，不能把 `/api/entries` 当标准路径

**问题**：OTT adapter 的 `/api` 同时承载管理、脚本、删除、调度等私有能力。把 `/api/entries` 作为 typetype 标准客户端 fallback 会重新耦合管理面和只读分发面，并让大文本退化成全量正文分发。

**现状**（2026-07-10 ADR-009 首轮落地）：
- OTT 标准客户端边界是 `/ott/v1` Service Profile 或 Static Profile
- `OttTextProvider.get_catalog()` 优先读 `/ott/v1/sources`，再 fallback 到 Static `/sources.json`，最后 fallback 到旧 `registry_index.json`
- `OttTextProvider.fetch_all_entries()` 优先读 `/ott/v1/entries`
- `/ott/v1` 不可用时按 Static Profile → 旧静态 `registry_index.json` + `content/{source_key}.json` fallback，不 fallback `/api/entries`
- inline OTT 条目通过 `loadOttEntry(entry_id)` 显式加载，不靠 `entry_id` 前缀猜测
- segmented OTT 条目通过 `OttSegmentProvider` 接入通用分片管线，进度 key 为 `ott:{authority}:{entry_id}@{revision_id}`
- `OttClient` 负责 Service Profile / Static Profile 读取顺序；`OttTextProvider` 负责缓存与 legacy fallback
- `registry_text_provider.RegistryTextProvider` 只保留兼容导出，新代码禁止继续依赖旧模块名

**正确做法**：
- 新增 OTT 客户端能力 → 先扩展 `/ott/v1` 或 Static Profile，再改 typetype
- 管理/脚本能力 → 留在 adapter Admin Profile `/ott-admin/v1`（旧 `/api` 仅兼容），typetype 只读客户端不要依赖
- 大文本 → 使用服务端定义 segment；不要在 typetype 侧拉完整正文再自行切片

**历史**：2026-07-10 ADR-009 首轮实现；2026-07-12 完成 `OttTextProvider` 命名迁移与 OTT adapter `/ott-admin/v1` 管理面拆分；2026-07-13 完成 source catalog、schema/validator、兼容测试包收口。

### ⚠️ 晴发文（Wenlai）不得 CI 化，必须保持即时拉取

**问题**：在评估「Registry/CI 化」提案时，曾误判晴发文（`wenlai_provider.py`）也适用。实际上晴发文是即时交互 API（`/api/texts/random` 每次返回不同内容），CI 化会破坏 random 语义且违反账号模型（CI 持账号 = 账号共享）。

**现状**（保持现状不动）：
- 独立 Port：`ports/wenlai_provider.py`
- 独立 Gateway/Adapter/UseCase：`wenlai_provider.py` → `wenlai_gateway.py` → `load_wenlai_text_usecase.py`
- 走 Worker：`presentation/adapters/wenlai_adapter.py` 已用 `_run_worker()`
- token 存储：`integration/secure_token_store.py`

**正确做法**：
- 晴发文是第 3 层（即时拉取）的参照实现，保持不动
- 未来若有第 2 个带认证的实时源，再抽象 `AuthenticatedRemoteProvider` Port（YAGNI）
- 不得将晴发文纳入 Registry/CI 体系或 `TextSourceConfig.sources`

**历史**：2026-07-05 ADR-008 §4.1 决策。

### ⚠️ L1 规则解释器必须保持无图灵完备性

**问题**：OTT Repo `ott-rule` 允许 repo 维护者在 manifest 中内联声明式抓取规则。如果解释器设计不当，可能引入任意代码执行面，破坏"客户端从网络订阅的一切内容均无任意代码执行"的不变式。

**现状**（2026-07-27 实现）：
- 解释器：`src/backend/integration/ott_rule_interpreter.py`（`OttRuleInterpreter`）
- `extract` 仅限 JSON path（`$.a.b`）、命名正则（`(?P<name>...)`）、CSS 选择器三选一
- `transform` 仅限 `trim` / `replace` / `truncate` 固定管道
- `request.url` 仅允许公网 http(s)；禁 `file:`、环回、私有地址（`validate_url()`）
- 单次 fetch ≤ 1 MB；总条目 ≤ 1000；max_pages 硬限制 20
- 调试工具：`scripts/debug_rule.py`（离线 CLI，不启动 UI）

**正确做法**：
- 扩展提取能力 → 仍走声明式（新增 JSON path 语法或 CSS 伪类），不得引入 JS/Python/动态 URL 计算
- 新增 transform 操作 → 在 `apply_transforms_to_entry()` 白名单中添加，不得允许任意字符串运算
- 规则源产出 entry 的 authority = `rule:{rule_id}`，进度键 `ott:rule:{rule_id}:{entry_id}@{revision_id}`
- 不得在解释器中执行网络请求以外的 I/O（禁文件写入、禁子进程）

**历史**：2026-07-27 ADR-010 Phase 3 落地。

### ⚠️ ott-script 必须经过 AST 安全检查 + 沙箱执行

**问题**：OTT Repo `ott-script` 允许 repo 维护者分发 Python 脚本到客户端执行。如果沙箱设计不当，恶意脚本可以执行任意系统命令、窃取数据。

**现状**（2026-07-27 实现）：
- 安全检查：`src/backend/integration/ott_script_safety.py`（`validate_script_source()`）
- 沙箱执行：`src/backend/integration/ott_script_client.py`（`ScriptSandbox`）
- 禁止：`eval`/`exec`/`compile`、`os.system`/`subprocess`/`socket`/`ctypes`、`importlib.import_module` 动态导入
- 允许：`httpx`/`json`/`re`/`hashlib`/`base64`/`Crypto`/`bs4` 等白名单模块
- 脚本必须定义 `fetch_entries() -> list[dict]`，返回标准化 entry
- 缓存：`ScriptCache`（TTL + AST 校验 + 原子写 + 离线回退）

**正确做法**：
- 新增脚本能力 → 在 `ALLOWED_MODULES` 白名单中扩展，不得绕过 AST 检查
- 脚本产出 entry 的 authority = `script`，进度键 `ott:script:{entry_id}@{revision_id}`
- 不得在沙箱中开放文件系统写入（除临时目录）、子进程创建、原始网络监听

**历史**：2026-07-27 ADR-010 Phase 3 落地。

---

## 文档编写规范

- **事实文档**（ARCHITECTURE.md）：先结论后解释。代码块标注语言。
- **Agent 规则**（本文档）：简洁直接。陷阱包含：问题、原因、正确做法、历史记录。
- **速查表**（docs/reference/*）：纯表格，H1 + `>` 摘要行 + 表格主体。不写段落。≤ 200 行。
- **操作手册**（docs/guides/*）：只写步骤、命令、验证方式。架构背景指向 ARCHITECTURE.md。
- **历史归档**（docs/history/*）：完整记录背景、决策、实现、验证。不修改、不删除。
