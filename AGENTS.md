# typetype 项目开发指南
<!-- 状态: active | 最后验证: 2026-08-13 -->

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
4. **本文档 §4-7** — 测试策略、平台权限、CI
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

`config.json` 是唯一的运行时配置文件，位于 `~/.config/typetype/config.json`（`schema_version=2`，ADR-013）。

| 文件 | 位置 | 内容 | 写入者 |
|:--- |:--- |:--- |:--- |
| `config.json` | `~/.config/typetype/` | 运行时配置（`ott`/`update`/`source_repos`/`wenlai`/`ai`/`ui` 段、本地 `text_sources` 等） | `RuntimeConfig`（主）、`RinUI AppUIConfigManager`（ui 字段） |
| `font_config.json`（已废弃） | `~/.config/typetype/` | 读屏字体路径 | 旧文件在 v1 → v2 迁移时合并进 `config.json.ui.reader_font_path`（文件保留不删） |

`RuntimeConfig` 设计要点：
- `dataclass` 结构：顶级字段 + 子 Config dataclass（`WenlaiConfig`、`AiConfig`、`OttConfig`、`UpdateConfig`、`TextSessionConfig`、`SourceReposConfig`）
- `schema_version=2`：缺版本（=v1）→ 一次性幂等迁移并写回 stamp v2；已是 v2 直接加载
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

**绑定规则**：Presentation 禁止依赖 Integration/Infrastructure 与 Domain 实体/存储；允许直连纯业务服务（`TypingService`/`CharStatsService`，见 [ARCHITECTURE.md 依赖规则](../docs/ARCHITECTURE.md#依赖规则)）。Bridge 不得直接访问 `SessionContext` 或持有 Integration 对象，状态访问一律经对应 Adapter 代理。

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
- 所有载文场景统一在 `TextLoadHubPage.qml` 中通过顶部 RinUI `Segmented` 切换 6 个来源 tab（本地文库/开源文库/练单器/晴发文/AI 推荐/自定义）；各来源共享同一组分片/达标组件，不再分散为多个独立入口页。开源文库 tab 按订阅源分组展示联邦聚合条目（`RepoEntriesPanel`，选中即载入；源组头可展开/收起/刷新/管理），订阅管理收敛到源组头弹窗 `RepoConfigDialog`（独立管理页 `ReposManagementPage` 已删除）

---

## 4. 测试策略

- 优先覆盖用例层与核心逻辑，不依赖真实 UI
- 对网络错误、超时、解析异常必须有测试
- 新增文本来源时补充：`LoadTextUseCase` 测试 + `GlobalExceptionHandler` 测试 + service/integration 测试

---

## 5. 服务端接入（已移除）

typetype-server 已随 [ADR-013](./docs/decisions/013-converge-to-three-repo-model.md) 全部移除：排行榜、成绩上传、登录注册、远程文本列表、`text_id` 回查、`base_url`/`api_timeout` 均删除。客户端收敛为三仓模型（typetype / open-typing-texts / ott-source-hub）空壳客户端，OTT 统一走 `source_repos` 订阅，晴发文/AI 为独立第三方即时源。

> 原服务端 API 文档已归档到 `docs/history/api-endpoints.md`。新增协议能力 → 先扩展 OTT Core / OTT Repo 协议（open-typing-texts 仓）再改 typetype；新增带认证实时源 → 参考晴发文完整独立 Pipeline。

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
| `build-release.yml` | Linux/Windows Nuitka 打包与 release；`assert-version` job 断言发布 tag / `pyproject.toml` / `src/backend/version.py` `APP_VERSION` 三者一致，并运行 `scripts/gen_version_manifest.py` 生成签名 `version.json` |

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

**问题**：本地文本加载曾在主线程同步执行导致 UI 阻塞（旧实现隐含同步 HTTP 回查）。

**正确做法**：所有加载统一走 Worker。两阶段异步：Worker 只读文件 → daemon thread 异步回查（现本地载文已无回查，OTT 订阅走 `RegistryAdapter` Worker）。

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

**现状**（2026-07-04 重构 + 2026-08-13 v2 收口后）：
- `RuntimeConfig._save_to_file()` 以 `_to_dict()` 为基全量写入，合并未知字段（前向兼容）
- 写入时加 `fcntl.lockf` 文件锁防止并发冲突
- `ui` 字段已成为 `RuntimeConfig` 的一等公民，通过 `update_ui_config()` 写入
- `font_config.json` 已并入 v1 → v2 一次性迁移：`reader_font_path` 折叠进 `config.json` 的 `ui.reader_font_path`（旧文件保留不删），不再是独立的运行期迁移点

**已知限制**：
- RinUI `AppUIConfigManager` 仍直接读写 config.json 的 `ui` 字段（RinUI 框架内部机制），与 RuntimeConfig 的 `_save_to_file` 存在理论上的并发窗口，但 Python 单线程模型中风险极低

**正确做法**：
- 增加配置字段 → 加在 Config dataclass 上 + `_from_dict` + `_to_dict`，不要绕开 RuntimeConfig
- 修改 UI 配置 → 通过 `runtime_config.update_ui_config(key=value)`，不要直接写文件
- 新子配置 → 遵循 `WenlaiConfig / AiConfig / OttConfig / UpdateConfig` 模式：`@dataclass` + `__post_init__` 范围校验 + `_from_dict` 负责 JSON 类型转换

**历史**：2026-07-04 多相位重构；2026-08-13 v2 schema 收口（ADR-013）。

### ⚠️ OTT Repo 控制面订阅统一走 `source_repos`（`registry.primary_url` 已删除）

**问题**：ADR-010 落地后，客户端多 authority 订阅统一走 `RuntimeConfig.source_repos`（`SourceReposConfig`）。旧 `registry.primary_url` / `mirror_url` 曾作为兼容标识保留，现随 ADR-013 v2 schema **整体删除**——配置段中不再存在这两个字段，单实例 OTT 数据面（`OttTextProvider` / `RegistryTextProvider` / `registry_index.json` fallback）一并移除，OTT 只走 `source_repos` 联邦。

**现状**：
- `SourceReposConfig` 是一组 `SourceRepoEntry`（url / enabled / trust_state / pinned_pubkey / refresh_ttl_seconds / etag / added_at / last_snapshot_hash）
- 旧 `registry.primary_url` 仅在 v1 → v2 迁移中按等价订阅保留（已存在 `source_repos` 时不重复）；`base_url`/`api_timeout` 直接丢弃
- 订阅增删改通过 `RuntimeConfig.add_source_repo / remove_source_repo / set_source_repo_enabled / set_source_repo_trust`，不要直接操作 `source_repos.repos` 列表
- manifest 拉取与缓存在 `RepoManifestCache`（TTL/stale-while-revalidate/原子写/后台刷新，复用 OTT Core v1 缓存决策树）
- 联邦聚合在 `OttFederationProvider`：按 authority 命名空间隔离，同 authority 多镜像按 priority + 健康度指数退避 failover

**正确做法**：
- 新增订阅 → `runtime_config.add_source_repo(url)`
- 扩展 manifest 能力 → 改 `validate_repo_manifest()` + `SourceRepoEntry`，遵循 OTT Repo v1 草案
- 消费订阅列表 → 通过 `RegistryAdapter`（Worker 异步），不要在主线程拉取 manifest
- 新子配置字段 → 加在 `SourceRepoEntry` + `_parse_source_repos` + `_to_dict`，保持 RuntimeConfig 为唯一序列化者

**历史**：2026-07-26 Phase 1 落地（ADR-010）；2026-08-13 `primary_url`/`mirror_url` 随 ADR-013 v2 schema 删除。

### ⚠️ TextSource 已收敛为 v2 纯本地模型（Loader/LeaderboardMode 已删除）

**问题**：旧的 `SourceType` 枚举与 `Loader`/`LeaderboardMode` 二维模型曾把"加载方式"和"排行榜行为"耦合在一起，且随 typetype-server 移除全部失效。

**现状**（2026-08-13 ADR-013 收口后）：
- `Loader` 收敛为仅 `LOCAL_FILE`，`LeaderboardMode` 枚举整体删除；`TextSourceEntry` 简化为 `{key, label, local_path}`，全部为本地文件
- OTT 订阅不再进 `text_sources`：源仓库条目统一在 `source_repos`，由 `RegistryAdapter` 聚合到载文中心「开源文库」标签
- 旧 `source_type` / `has_ranking` / `loader` / `leaderboard_mode` 迁移分支随 v1 → v2 迁移一并删除

**正确做法**：
- 添加本地文本 → 在 `config.json` `text_sources` 加条目（`{label, local_path}`），或走设置页本地文本导入
- 添加远程文本 → 订阅 OTT Repo 源仓库，或新增独立 Provider 栈（参考晴发文）；不要改 `text_sources` 结构
- `TextSourceEntry.is_local` 属性恒为 `True`，不要依赖 loader 判断

**历史**：2026-07-04 重构引入二维模型；2026-08-13 随 ADR-013 删除。

### ⚠️ 开源文库缓存层必须读缓存，禁止直打网络

**问题**：开源文库 provider 的 `_cache_dir` 曾长期只创建不读写，所有请求直打网络，弱网/离线即崩（`cache_ttl_seconds` 是死字段，`cache_dir` 创建但无读写）。

**现状**（Phase 1a/1b 实现，2026-08-13 移至 `OttCachedFetcher`）：
- `OttCachedFetcher.fetch_json_with_cache()` 实现缓存决策树：cache hit → stale-while-revalidate → cache miss → 网络成功写缓存 → 离线兜底（`read_cache`/`write_cache`/`is_cache_expired`/`cache_path`）
- 基于文件 mtime + `ott.cache_ttl_seconds`（默认 3600s）判断过期
- 原子写：tmp + `Path.replace`，全方法 `try/except OSError` 兜底
- 后台刷新：`AsyncExecutor` + `threading.Lock` 去重防重复刷新
- 旧 `OttTextProvider` 已删除，缓存实现在 `integration/ott_cached_fetcher.py`，由联邦/规则/脚本客户端复用
- **jsDelivr CDN 降级（2026-08-14）**：`fetch_json_with_cache`/`fetch_text_with_cache` 主地址失败时按 `to_jsdelivr_url`（`ott_normalization.py`，raw.githubusercontent.com → cdn.jsdelivr.net）重试 CDN；`ScriptCache._download_limited` 同样兜底（脚本下载曾裸打 raw 超时）。manifest 拉取（`RepoManifestCache`）自 2026-08-13 已有同款降级，现统一到 `ott_normalization.to_jsdelivr_url`
- **force 参数（2026-08-14）**：`fetch_json_with_cache(..., force=True)` / `fetch_text_with_cache(..., force=True)` 绕过缓存读、直接拉取并写回——手动刷新不得被 TTL 缓存拦截（失败时返回 None，不读旧缓存）

**正确做法**：
- 修改 Registry 相关逻辑 → 通过 `fetch_json_with_cache()` / `fetch_text_with_cache()` 走缓存层，不要绕过 `read_cache`/`write_cache`
- 新增缓存路径 → 复用 `cache_path(cache_key)` 统一文件布局
- 缓存写入失败/读取失败 → 静默返回 None，不要阻塞主流程
- 主地址失败 → 让 `_fetch_json/_fetch_text` 走 jsDelivr 兜底，不要在调用方重复造降级；非 raw.githubusercontent.com URL 不会触发

**历史**：2026-07-05 Phase 1a/1b 实现，ADR-008 §决策；2026-08-13 随 `OttTextProvider` 删除迁移到 `OttCachedFetcher`（ADR-013）；2026-08-14 jsDelivr 降级统一 + force 参数。

### ⚠️ typetype 只能依赖 OTT 只读协议，不能把 `/api/entries` 当标准路径

**问题**：OTT adapter 的 `/api` 同时承载管理、脚本、删除、调度等私有能力。把 `/api/entries` 作为 typetype 标准客户端 fallback 会重新耦合管理面和只读分发面，并让大文本退化成全量正文分发。

**现状**（ADR-009 首轮落地 + 2026-08-13 ADR-013 收口后）：
- OTT 标准客户端边界是 `/ott/v1` Service Profile 或 Static Profile
- 目录/条目读取由 `OttFederationProvider` 统一承担（按 `source_repos` 订阅联邦聚合），优先读 `/ott/v1/sources`、`/ott/v1/entries`，再 fallback 到 Static Profile
- 旧 `OttTextProvider` / `RegistryTextProvider` / `registry_index.json` 单实例数据面与 legacy fallback 已整体删除（ADR-013）
- inline OTT 条目通过联邦路径 `loadFederatedInlineEntry(authority, entry_id, revision_id)` 显式加载，不靠 `entry_id` 前缀猜测
- segmented OTT 条目通过 `OttSegmentProvider` 接入通用分片管线，进度 key 为 `ott:{authority}:{entry_id}@{revision_id}`
- `OttClient` 负责 Service Profile / Static Profile 读取顺序（manifest `endpoints[].profile` 显式声明时尊重声明、只探测对应 profile）；缓存复用 `OttCachedFetcher`

**正确做法**：
- 新增 OTT 客户端能力 → 先扩展 `/ott/v1` 或 Static Profile，再改 typetype
- 管理/脚本能力 → 留在 adapter Admin Profile `/ott-admin/v1`（旧 `/api` 仅兼容），typetype 只读客户端不要依赖
- 大文本 → 使用服务端定义 segment；不要在 typetype 侧拉完整正文再自行切片

**历史**：2026-07-10 ADR-009 首轮实现；2026-07-12 完成 `OttTextProvider` 命名迁移与 OTT adapter `/ott-admin/v1` 管理面拆分；2026-07-13 完成 source catalog、schema/validator、兼容测试包收口；2026-08-13 `OttTextProvider`/`registry_text_provider` 删除（ADR-013）。

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
- 不得将晴发文纳入 OTT Repo 订阅体系或 `TextSourceConfig.sources`

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

**schema v2**（2026-08-07 Phase 1.3 落地，设计见 `docs/designs/ott-dsl.md`）：
- `steps`：DSL 顺序管道（`ott_dsl.py` 45 原语白名单求值器），`{"ref": "body"}` 引用 `request.body` 字面量，末步输出作为 POST 请求体
- `permissions.network`：域名白名单（子域匹配），声明时生效——URL 不在白名单内整条规则拒绝；未声明回退 `validate_url`
- `rights.min_api_level`：客户端 API level（`CLIENT_API_LEVEL` 常量，federation 创建 interpreter 时传入）低于声明值 → 规则不兼容跳过
- body 类型规范化：str/bytes 直传、dict/list → JSON 序列化、int/bool 字符串化、其余类型规则拒绝；`Content-Type` 必须由规则 `request.headers` 显式声明
- 校验拒绝：`transform` 与 `steps` 并存、未知原语、steps 超限 → 整条规则跳过

**正确做法**：
- 扩展提取能力 → 仍走声明式（新增 JSON path 语法或 CSS 伪类），不得引入 JS/Python/动态 URL 计算
- 新增 transform 操作 → 在 `apply_transforms_to_entry()` 白名单中添加，不得允许任意字符串运算
- 规则源产出 entry 的 authority = `rule:{repo_id}:{rule_id}`（上游规范，防跨 repo 冲突），进度键 `ott:rule:{repo_id}:{rule_id}:{entry_id}@{revision_id}`
- 不得在解释器中执行网络请求以外的 I/O（禁文件写入、禁子进程）
- 扩展 DSL 原语 → 在 `ott_dsl.py` 的 `PRIMITIVES` 注册表添加，保持纯函数无状态；引擎约束常量（`MAX_VALUE_BYTES`/`MAX_DEPTH`/`MAX_CALLS`/`MAX_STEPS`）不得放松

**历史**：2026-07-27 ADR-010 Phase 3 落地；2026-08-07 Phase 1.1/1.2 受限原语引擎 + Phase 1.3 schema v2。

### ⚠️ ott-script 必须经过 AST 安全检查 + 沙箱执行

**问题**：OTT Repo `ott-script` 允许 repo 维护者分发 Python 脚本到客户端执行。如果沙箱设计不当，恶意脚本可以执行任意系统命令、窃取数据。

**现状**（2026-07-27 实现，含子进程沙箱修复）：
- 安全检查（第一道关卡）：`src/backend/integration/ott_script_safety.py`（`validate_script_source()`）— AST 白名单 import + 别名解析 + `__builtins__` 检测
- 沙箱调度：`src/backend/integration/ott_script_client.py`（`ScriptSandbox`）— 写临时文件 + 启动子进程 + 解析 stdout JSON
- 子进程沙箱（最后防线）：`src/backend/integration/ott_script_runner.py` — 独立 Python 进程 + 资源限制（256MB 内存 / 30s CPU / RLIMIT_NPROC=0 / 10MB 文件写入）+ 受限 builtins + 白名单模块注入 + Landlock 文件系统白名单（ctypes 直调 syscall，本机无 `os.landlock_*`）+ stdout JSON 序列化
- 禁止：`eval`/`exec`/`compile`、`open`、`os`/`subprocess`/`socket`/`ctypes`/`import`（均不在白名单）、`__builtins__` 引用
- 允许：`httpx`/`json`/`re`/`hashlib`/`base64`/`Crypto`/`bs4` 等白名单模块
- 脚本必须定义 `fetch_entries() -> list[dict]`，返回标准化 entry
- 缓存：`ScriptCache`（TTL + AST 校验 + 原子写 + 离线回退）

**正确做法**：
- 新增脚本能力 → 在 `ALLOWED_MODULES` 白名单中扩展，不得绕过 AST 检查
- 脚本产出 entry 的 authority = `script`，进度键 `ott:script:{entry_id}@{revision_id}`
- 安全边界为子进程隔离：脚本逃逸最多获得 256MB 内存 + 30s CPU，无法写主进程内存；`RLIMIT_NPROC=0` 禁止 fork；网络可访问（抓取需要）但受 CPU 时间约束；Landlock（内核 5.13+，不可用时静默降级）将文件系统访问限制在脚本目录 + `sys.prefix` + `/etc` + `/dev` 白名单，逃逸读取任意文件被内核拒绝

**历史**：2026-07-27 ADR-010 Phase 3 落地。

### ⚠️ manifest 验签与 snapshot 链必须以网络原始字节为口径

**问题**：`_accept_manifest` 曾对 `validate_repo_manifest()` 归一化重构后的 dict 验签并计算 `last_snapshot_hash`。归一化会补默认字段、重建嵌套（mirrors/sources/trust）、strip 字符串——canonical JSON 字节与生产方签发内容不同，生产路径验签必失败（verified 永远不可达）、防回滚必误判。

**正确做法**：
- `_verify_trust` 接收网络原始 dict（剔除 `trust` 字段后 canonical 验签）；`last_snapshot_hash` 用 `manifest_hash(data)`（raw 整体含 trust）
- 缓存写**网络原始内容**，读取时经 `_read_validated_cache()` 归一化后再消费（校验失败视为无缓存）
- **先验签后落盘**：签名 failed / 首次有效签名 / 公钥变更 / key 级撤销 / pending 粘性 → 拒绝替换缓存（TOFU 未确认内容不服务，服务旧缓存或空）
- revocations 仅在验签通过（verified）时应用；无签名 manifest 接受（unverified）但不应用 revocations（防伪造屏蔽投毒）
- 改验签/链逻辑时禁止对归一化 dict 操作；新测试须用真实 ed25519 密钥对 raw manifest 签名

**历史**：2026-08-12 边界审计修复（修复前生产路径验签恒失败）。

### ⚠️ 沙箱启动序列：能力探测必须早于 RLIMIT_NPROC，seccomp 必须显式调用

**问题**：`ott_script_runner.py` 的 `_apply_seccomp()` 曾**零调用**（构造了 BPF 从未安装）；且 `seccomp_available()` 探测需 fork 子进程，但 `_set_resource_limits()` 已设 `RLIMIT_NPROC=(0,0)` → 探测恒 False → seccomp 恒跳过（双重失效）。另：白名单模块预导入原发生在 Landlock 之后，Crypto 等 C 扩展 dlopen 会被文件系统白名单拒绝。

**正确做法**（main() 顺序固定，不可调换）：
1. `landlock_available()` + `seccomp_available()` 探测（必须在 RLIMIT_NPROC=0 之前，结果缓存）
2. `_preload_allowed_modules()`（Landlock 前触发 .so 加载）
3. `_set_resource_limits()` → `_apply_landlock()` → `_apply_seccomp()` → `run_script()`
- Landlock 探测可用但安装失败（add_rule/restrict_self 抛错）→ raise RuntimeError 拒绝执行，不静默裸奔
- `ALLOWED_MODULES` 禁止含 `builtins`（脚本 `import builtins` 即拿到真实 eval/open/exec）
- 新增 runner 能力时先确认 main() 序列；seccomp 任何改动须同时更新 `seccomp_available` 探测与调用点

**历史**：2026-08-12 边界审计修复。

### ⚠️ 进度持久化编排残留：Bridge 直持 TextSliceProgressStore（待下沉）

**问题**：进度序列化/恢复/存储编排仍散落在 Bridge（`collectSliceResult`/`_update_progress_current_slice`/`applySliceMode`），Bridge 构造直持 `TextSliceProgressStore`（integration 对象），违反 ARCHITECTURE.md "Bridge 直接持有 Integration 对象 ❌"。2026-08-12 已消除 Bridge 直取 `_session_context` 的 4 处穿透（统一经 `TypingAdapter` 代理：`restore_slice_progress()`/`get_slice_progress_snapshot()`/`get_slice_criteria_text()`/`slice_text`，`SessionContext.slice_progress_state()` 为状态拥有者自序列化），但 store 编排仍在 Bridge。

**正确做法**：下沉到 Application 层（方案 B）：`TextSliceProgressStore` 经 Port 协议注入 UseCase，Bridge 收敛为纯 Slot 转发。`SessionContext` 的自序列化接口（`slice_progress_state()`/`apply_metrics_dict()`/`slice_text`）已就位，是下沉的前置。

**历史**：2026-08-12 边界审计发现，同日消除 bridge 穿透（方案 A）；store 下沉留待后续批次。

### ⚠️ OTA 版本一致性：`APP_VERSION` / `pyproject.toml` / 发布 tag 三处必须同步

**问题**：`src/backend/version.py` 的 `APP_VERSION` 是**运行期**版本单一事实源（Nuitka 独立产物内不可读 pyproject.toml）；`pyproject.toml` version 是**构建期**来源；发布 tag（`v*`）是 release 标识。三者脱节会导致 OTA 更新检查拿不到匹配资产或跳过更新。

**正确做法**（ADR-014）：
- 改动版本号时三处必须同步修改；`build-release.yml` 的 `assert-version` job 会断言 tag == `pyproject.toml` == `APP_VERSION`
- 发布流程：`scripts/gen_version_manifest.py` 生成并签名 `version.json`（含各平台资产 sha256），作为 release 资产附上
- 版本降级/跳过由更新检查逻辑处理；客户端不发布测试版号（`channel` 预留 stable/beta）

**历史**：2026-08-13 ADR-014 落地。

### ⚠️ 动态源条目必须物化落盘，选中载入不得重新执行规则/脚本

**问题**：rule/script 源每次执行返回随机内容，`get_entry(authority, entry_id)` 重抽会与列表 entry_id 失配（实测 `get_entry('2b96d8...') → None`）。

**正确做法**：联邦列表物化结果写 `EntrySnapshotStore`（磁盘快照），`load_entry` 快照命中直接返回；刷新只是换新（保留最近 N 条）。on_demand 源（每次随机）不得进入自动调度（防无限刷新循环），仅手动「抽新」。新增刷新策略 → 扩展 `RefreshPolicy` 模式；用户 per-source 覆盖走 `RuntimeConfig.set_source_refresh_override`。

**刷新语义（2026-08-14 修正）**：rule/script/bridge 条目内存缓存（`_EntryCache`，TTL=`ott.cache_ttl_seconds`）与 instance 文件缓存**曾拦截手动刷新**——TTL 内点刷新按钮返回旧条目，且 `refresh_source` 先全量列所有源再过滤（O(N) 浪费 + 全源随机源重抽）。现在：
- 手动刷新一律 **force 绕过缓存**：总刷新 `refreshFederatedAll`（全部源强制换新）→ `registry_adapter.refreshAllSources` → `catalog.refresh_and_list_all(force=True)` → `federation.list_all_entries(force=True)`；repo 级刷新 `refreshFederatedRepo(repo_id)` → `catalog.refresh_repo` → 该 repo 下各 authority 逐个 `federation.refresh_source(authority)`（**只物化该 repo**，其他 repo 零调用）
- force 穿透链路：`_EntryCache.get(key, force=True)` → 各 client `list_entries(force=True)` → `OttCachedFetcher.fetch_*(..., force=True)`（绕过缓存读，失败返回 None 不读旧缓存）
- **自动调度不受影响**：`RefreshScheduler`/`scheduled_tick` 仍只刷 interval 到期源，`on_demand` 仅手动抽新（防无限刷新循环）
- **刷新按组件层级作用域**：右侧面板「刷新」repos 时 = 全部源换新（该层级列表即联邦聚合）、左栏列表顶部刷新 = 全部源换新、**源组头刷新 = 订阅源（repo）级换新**（`refreshFederatedRepo(repo_id)` → `catalog.refresh_repo` → 该 repo 下全部 authority 逐个 `federation.refresh_source`（force），其他 repo 零调用）。**视图必须走 `catalog.list_cached()` 纯读**（不能走 `refresh_and_list_all`——那会重新物化其他源（缓存冷时打网络）并把所有源快照 `captured_at` 重置，freshness 徽章被污染）。**刷新动画同样按层级作用域**：列表级刷新置 `entries_loading` 盖整列表动画；repo 刷新**不置列表级 loading**，只标记 `refreshingFederatedRepo`（Bridge 代理 `RegistryAdapter.refreshing_repo`）。**`RepoEntriesPanel` 按订阅源（repo）动态分组**：条目物化时 federation `_decorate_with_repo_meta` 注入 `_repo_id/_repo_name/_repo_url/_repo_max_entries`（authority→repo 映射随 `_build_clients` 缓存构建，**纯动态归属不硬编码**）——条目属于哪个订阅源就归入哪个源组。组头 = 展开/收起 + 源名 + **条目计数（x / 上限，上限来自 manifest 可选字段 `max_entries`，缺失=无上限）+ 源级刷新按钮/动画（一份）+ 管理按钮**；卡片只保留 freshness 徽章，刷新操作收敛到组头。组头点击 = 展开/收起（`_expanded` 状态，折叠时组内条目不渲染）。**管理弹窗 `RepoConfigDialog` 取代独立管理页**（`ReposManagementPage`/`ReposManagementPanel` 已删除）：组头「管理该源」打开弹窗（启用/信任确认/删除订阅）；「添加订阅」在列表头部弹窗输入 URL。**删除订阅连带清理快照**：`removeRepo` → `federation.repo_id_of_url` + `catalog.remove_repo` → `store.clear_authority`（逐 authority 删快照目录），随后重发条目列表；列表级刷新开始时清除 repo 标记。**delegate 双组件（Loader）**：header/entry 各自只引用自己的 role——不可见分支的绑定也会求值，混用 `model.group`/`model.entry` 会对 undefined role 抛 TypeError（2026-08-14 实测修复）。**两个组件必须声明为 delegate `Loader` 的直接子项**：Loader 实例化「外部声明的 Component」时，加载项的 QML 上下文是组件声明处（ListView 作用域），看不到 delegate 的 `loader` id 与 `model`/`index` 上下文属性——曾把组件声明在 ListView 下，全部 header/entry 绑定抛 `ReferenceError: loader is not defined` / `model is not defined`（2026-08-14 全应用实测）。声明为 Loader 子项后加载项继承 delegate 上下文，`loader.groupData`/`loader.entryData`/`model.*` 均可解析
- **条目刷新硬超时兜底（2026-08-14 恢复）**：旧 `loadAllEntries` 曾有 15s QTimer 兜底，`loadFederatedEntries` 重构时丢失——网络请求各有 timeout，但一个 worker 任务串行多请求/多页/脚本+条目总时长可能很长，某环节 hang（DNS 挂起等）时 worker 永不完成、loading/动画永转。现 `RegistryAdapter` 统一 `_ENTRIES_REFRESH_TIMEOUT_S=45` 单发 QTimer：`refreshRepoEntries`/`refreshAllSources`/`_revalidate_entries`（quiet）启动，到点只清理状态（`refreshing_repo`/`entries_loading`/`_entries_revalidating`）+ 手动刷新发「刷新超时，请检查网络」（revalidate 静默保持快照视图），**不等待 worker 线程**（worker 之后完成仍正常重发列表，无害）；操作已提前完成 → 陈旧超时经状态检查直接忽略

**进入开源文库视图 = 当前快照存储（永久语义，2026-08-14）**：`loadFederatedEntries` → `RegistryAdapter.loadFederatedEntries` 先**同步**读 `catalog.list_cached()`（`EntrySnapshotStore.list_all` 只读已落盘快照，零网络、不白屏），随后**后台非强制** `refresh_and_list_all()`（仅 TTL 过期源重抓）完成后**原地更新**列表（不置 loading、不触发错误态）。每次查看都成立（非仅首屏）——快照存储本就是列表唯一事实源，过期/prune/手动刷新（force）只换新存储，视图永远等于存储。后台 revalidate 失败静默（保持已显示的快照视图）；进行中重复进入不叠加（`_entries_revalidating` 去重）。

**revalidate 不虚刷 freshness（2026-08-14）**：`refresh_and_list_all` 非 force 路径对**内容未变**的快照跳过 save（快照 `snap_fingerprint` 指纹比对），保留原 `captured_at`——缓存命中的源不再被重置成「刚刚/最新」（曾无条件 `save(captured_at=now)`，每次进入 tab 所有源徽章被虚刷）。内容真正变化（TTL 过期源重抓返回新内容）或手动 force（`refreshAllSources`/`refresh_source`，确实重新抓了）才更新 `captured_at`。指纹由 catalog 层 `_content_fingerprint` 按内容相关字段（title/preview/content/char_count/content_mode/revision/segment/tags 等）规范化哈希自算——instance 摘要（`normalize_summary`）与 rule/script/bridge 条目没有统一 `content_hash`；旧快照无指纹 → 首次 revalidate 视为已变并补写（一次性），之后稳定。

**⚠️ 刷新视图不得收缩（2026-08-14 回归修复）**：`refresh_and_list_all` 的返回值**必须等于当前全部已存快照**（物化只更新存储，返回 `list_cached()`），不能只返回本次物化成功的源——曾因网络失败/超时的源整个从视图消失（「点击刷新后条目变少很多」），其快照明明仍在存储里。物化失败源保留旧快照（on_demand 恒「随机」徽章 / interval 标 stale），仍可载入；视图只随存储变化（过期/prune/force 换新），不随单次物化成败波动。

**已知边界**：快照条目级有界（`prune_stale` 每 authority 保留 N=5）；**删除订阅会连带清理该 repo 下全部 authority 的快照**（`catalog.remove_repo` → `store.clear_authority`），孤儿残留仅在非正常退出/手动删配置等路径下存在（GC/清理页为 spec 后续项，思路见 `docs/designs/dynamic-source-snapshot-freshness.md` §8）。**instance 源的列表物化是摘要（`normalize_summary`，无 `content` 字段）**，快照只有 preview——`load_entry` 必须对「快照命中但无正文」兜底 `federation.get_entry` 拉全文（静态端点按条目文件缓存，重复点击不重复打网络），否则内置 static 源载入跟打恒失败（回归：2026-08-13 实测修复）。rule/script/bridge 快照含 content，快照命中零重抽。

**联邦载文同步镜像本地链路（2026-08-14 修复闪退/无限加载）**：`loadFederatedEntrySegment` / `loadFederatedInlineEntry` **不再跨 worker 线程**构建/回传会话——旧实现 `_submit_to_thread_pool` 在子线程构造 `OttSegmentProvider`/`TextSessionUseCase` 并经 `textContentLoaded` 间接回传，实测 instance 源触发 **double free or corruption**（共享 httpx client 跨线程并发使用）、规则源 `textContentLoaded` 信号丢失导致「一直加载动画」（快照明明在却不载文）。现在与 `loadLocalArticleSegment` / `loadFullText` 一致：主线程同步建会话 + 直发 `textLoaded`（QML `applyLoadedText → handleLoadedText` 落地）。删除了 `_on_ott_segment_session_started`/`_build_federated_segment_session` 与 `textContentLoaded` 信号（零发射者）；QML 侧 `_pendingFederatedContent` 标志移除，busy 由常驻联邦 Connections 的 `onTextLoaded`/`onTextLoadFailed` 清除。

**历史**：2026-08-13 设计（docs/designs/dynamic-source-snapshot-freshness.md）与实现；2026-08-14 手动刷新 force 语义 + 单源刷新不再全量列源 + 进入 tab 读快照（首屏→永久：同步显示 + 后台 revalidate）+ 联邦载文同步化。

---

## 文档编写规范

- **事实文档**（ARCHITECTURE.md）：先结论后解释。代码块标注语言。
- **Agent 规则**（本文档）：简洁直接。陷阱包含：问题、原因、正确做法、历史记录。
- **速查表**（docs/reference/*）：纯表格，H1 + `>` 摘要行 + 表格主体。不写段落。≤ 200 行。
- **操作手册**（docs/guides/*）：只写步骤、命令、验证方式。架构背景指向 ARCHITECTURE.md。
- **历史归档**（docs/history/*）：完整记录背景、决策、实现、验证。不修改、不删除。
