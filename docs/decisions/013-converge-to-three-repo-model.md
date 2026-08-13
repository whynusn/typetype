# ADR-013: 收敛到三仓模型并移除 typetype-server 耦合

<!-- 状态: proposed | 决策日期: 2026-08-13 -->

> 本 ADR 是对「typetype 定位与能力边界」的一次收口。核心结论：**typetype 收敛为只依赖三仓模型（typetype 客户端 / open-typing-texts 协议+参考实现 / ott-source-hub 内容分发）的空壳客户端**，删除 typetype-server 及其排行榜/成绩/登录/远程文本全部耦合，并把配置系统改为带 `schema_version` 的幂等迁移，一次性清除所有 legacy 兼容层。

## 背景

调研发现三个相互叠加的问题，都指向同一个根因——**配置系统为兼容旧版本而长期打补丁，边界已经模糊**：

1. **两套并行的 OTT 子系统**：旧的单实例数据面 `OttTextProvider`（走 `registry.primary_url`/`mirror_url` + `registry_index.json`/`content/{key}.json` fallback）与新的联邦控制面 `OttFederationProvider`（走 `source_repos`）同时存活。ADR-010 决策 6 已宣布 `RegistryConfig → SourceReposConfig`「旧配置自动迁移」，但 `primary_url` 数据面仍被 `container.py:257-266`、`text_source_gateway.py:63-69`、`bridge.py:834-853` 接线，未真正收口。

2. **typetype-server 耦合面庞大但已名存实亡**：`base_url`/`api_timeout`/`RemoteTextProvider`/`AuthService`/`LeaderboardFetcher`/`ApiClientScoreSubmitter`/`TextUploader`/`text_id` hash 回查，以及 3 个榜单页 + 打字页内联榜单 + 🏆 按钮 + 登录注册对话框，全部指向开发阶段、未开放公网的 typetype-server（README.md:85）。本地打字/历史/字统计/晴发文/AI 均不依赖它。

3. **legacy 兼容层堆积**：`source_type`/`has_ranking` 迁移（`text_source_config.py:81-130`）、`font_config.json` 迁移（`bridge.py:2988-3016`）、`registry.primary_url` 自动迁移（`runtime_config.py:427-446`）、`RegistryTextProvider` 兼容别名（`registry_text_provider.py`）、`TextCatalogItem.has_ranking` 死字段（写 4 处、读 0 处）、`example.org` 运行时哨兵（`runtime_config.py:284-288`）。

**目标定位（三仓能力边界）**：

```
typetype         = 空壳客户端（读协议、沙箱执行 L3、本地缓存）—— 类比 mihon/kazumi 应用本体
open-typing-texts= 协议规范 + 参考适配器 + schema/fixtures —— 类比「扩展格式规范 + 参考扩展」
ott-source-hub   = 规则/脚本仓库 manifest —— 类比 mihon extension repo / kazumi 规则仓库
```

内容三方都不托管：规则/脚本只描述「怎么抓」，正文由客户端解释器/沙箱运行时从第三方 API 拉取。

## 选项

| 方案 | 描述 | 判断 |
|:---|:---|:---|
| A. 温和清理 | 只删纯死代码，保留 legacy 兼容与 server 入口，改文档标「废弃」 | ❌ 不解决混乱，兼容包袱与双子系统持续存在 |
| B. 彻底收敛 + 版本化迁移 | 删 typetype-server + legacy 层，配置加 `schema_version` 幂等迁移 | ✅ 选中 |
| C. 另起新 schema 并存双读 | 保留 v1 解析器 + 新增 v2，双路径长期共存 | ❌ 与 B 目标相同但多一套永久维护的旧解析器，违背「清除混乱」初衷 |

## 决策

1. **客户端空壳化，删除 typetype-server 全部耦合**。删除排行榜（3 榜单页 + 内联榜单 + 🏆 按钮）、成绩上传、登录注册、远程文本列表、`text_id` hash 回查。本地打字历史/字统计/成绩展示（`EndDialog` 复制成绩、`ScoreArea` 实时指标）保留。去中心化榜单交 ADR-012 独立推进，本次不留占位页。

2. **晴发文（wenlai）与 AI（LLM）保留**。它们是独立运行时第三方源（即时拉取/出题），不引用任何其他仓库，与三仓定位不冲突。晴发文继续作为 AGENTS.md 明确要求保留的第 3 层（即时拉取）参照实现。

3. **配置系统版本化 + 幂等静默迁移**。`config.json` 新增 `schema_version`（当前 `2`）。加载时：缺版本（=v1）→ 一次性迁移并写回 stamp v2；已是 v2 → 直接加载，无迁移逻辑。**无弹窗、天然幂等**（stamp 保证迁移只跑一次）。

4. **目标配置 schema（v2）**：
   - 删除：`base_url`、`api_timeout`、`registry.primary_url`、`registry.mirror_url`、`text_sources` 中的 server/registry 条目与 `loader`/`leaderboard_mode`/`source_type`/`has_ranking` 字段、`font_config.json`。
   - 保留：`source_repos`、`wenlai`、`ai`、`text_session`、`ui`（含 `reader_font_path`）、`blocked_content_hashes`、`typing_history_max_records`、`text_sources`（仅剩本地文件 `{label, local_path}`）。
   - 收纳：`registry.{cache_ttl_seconds, max_content_bytes, scripts_enabled}` → 新 `ott.{...}` 顶级段（三者是 OTT 运行时参数：`cache_ttl_seconds` 被 `ott_federation_provider.py:615,649` 用作 rule/script 缓存 TTL；`max_content_bytes` 被 `container.py:247` 传入 federation；`scripts_enabled` 是 L3 沙箱开关）。

5. **单实例 OTT 数据面整体移除，统一走 `source_repos` 联邦**。删除 `registry.primary_url`/`mirror_url`、`registry_index.json`/`content/{key}.json` fallback、`RegistryTextProvider` 兼容别名、`ott_legacy.py`、`OttClient` 的 primary/mirror 双 URL。依据：删 server 后 `Loader.REGISTRY` 唯一来源（legacy `source_type: "registry"` 迁移）已消失，单实例数据面不可达。

6. **清除 legacy 迁移死代码**。删除 `text_source_config.py` 的 `_LEGACY_SOURCE_TYPE_MAP` 与 `source_type`/`has_ranking` 迁移分支、`bridge.py` 的 `font_config.json` 迁移、`TextCatalogItem.has_ranking` 死字段（`text_catalog_item.py:11` + 4 处写入点）。

7. **`Loader` 收敛为仅 `LOCAL_FILE`，`LeaderboardMode` 枚举整体删除**。成绩上传移除后 `NONE`/`SERVER_RESOLVED`/`LOCAL_LOOKUP` 全部失效；`TextSourceEntry` 简化为 `{key, label, local_path}`。

8. **删除孤儿开发脚本**：`scripts/serve_ott_repo.py`（零引用，且 serve 的 `file://__BUILTIN_DIR__` 占位不做替换）、`scripts/test_federation.py`（无 `test_*`，未接 pytest/CI）、`scripts/validate_profile_layout_v2.py`（独立模型不读真实 QML）。保留 `scripts/debug_rule.py`（AGENTS.md 已记录为合法调试工具）。

9. **`example.org` 哨兵从运行时移除**。`_cleanup_stale_subscriptions()`（`runtime_config.py:284-288`）的占位订阅清理是一次性 legacy 动作，移入 v1→v2 迁移；RFC-2606 占位符本身（测试 fixture/docstring 示例）保留，健康无问题。

## 影响

### 迁移映射（v1 → v2）

| 旧字段/机制 | 处理 |
|:---|:---|
| `base_url`、`api_timeout` | 删除 |
| `registry.primary_url`、`registry.mirror_url` | 删除（已在 `source_repos` 中等价订阅则保留订阅） |
| `registry.cache_ttl_seconds`/`max_content_bytes`/`scripts_enabled` | → `ott.*` |
| `text_sources[]` 中 `loader=REMOTE_API`/`REGISTRY` 条目 | 丢弃 |
| `text_sources[]` 中 `LOCAL_FILE` 条目 | 重写为 `{label, local_path}` |
| `source_type`/`has_ranking` | 丢弃 |
| `font_config.json`（若存在且 `ui.reader_font_path` 为空） | 合并进 `ui.reader_font_path`，文件退役 |
| `example.org` 占位订阅 | 移除 |

### 删除文件（server 耦合，证据充分）

`integration/remote_text_provider.py`、`api_client_auth_provider.py`、`leaderboard_fetcher.py`、`text_uploader.py`、`score_retry_store.py`、`domain/services/auth_service.py`、`presentation/adapters/auth_adapter.py`、`leaderboard_adapter.py`、`workers/leaderboard_worker.py`、`text_list_worker.py`、`text_content_worker.py`、`score_submit_worker.py`、`ports/auth_provider.py`、`leaderboard_provider.py`、`score_submitter.py`、`text_uploader.py`、`utils/text_id.py`、`models/dto/auth_dto.py`、`integration/registry_text_provider.py`、`ott_legacy.py`、`scripts/serve_ott_repo.py`、`scripts/test_federation.py`、`scripts/validate_profile_layout_v2.py`。

### 删除 QML 文件

`TextLeaderboardPage.qml`、`DailyLeaderboard.qml`、`WeeklyLeaderboard.qml`、`AllTimeLeaderboard.qml`、`typing/LeaderboardPanel.qml`。

### 修改文件（mixed，保留但精简）

`runtime_config.py`（版本化 + `ott` 段 + 迁移）、`text_source_config.py`（收敛 Loader/删 LeaderboardMode）、`container.py`（删 server 装配）、`bridge.py`（删 server 槽/属性/信号 + font_config 迁移）、`main.py`（删登录初始化 + server URL 列表）、`text_source_gateway.py`（收敛本地加载）、`load_text_usecase.py`（删 text_id 回查）、`text_adapter.py`（删异步回查）、`typing_adapter.py`（删成绩提交）、`session_context.py`（简化上传状态机）、`upload_text_adapter.py`（删 cloud 分支）、`SettingsPage.qml`（删 base_url 卡片）、`ProfilePage.qml`（删登录对话框）、`TypingPage.qml`/`ToolLine.qml`（删排行榜/textId）、`TextLoadHubPage.qml` + `TextSourceBehaviors.js`（删 `jisubei` server tab；⚠️ 区别于 ott-source-hub 的 `jisubei` L1.5 DSL 规则源，后者保留）。

### 前置验证门（Phase 3 删单实例数据面前必须先做）

确认 `OttFederationProvider._InstanceClient`（`ott_federation_provider.py:119-188`）**完整覆盖** `OttTextProvider` 对 ott-instance 源的能力（`/ott/v1` + Static Profile 读取、segment 拉取、缓存）。若覆盖不全，则保留「无 legacy 版 `OttTextProvider`」供 federation 复用，而非整体删除。**此门决定 Phase 3 删减幅度，单独开验证任务。**

### 分阶段

```
Phase 0  配置版本化 + 幂等迁移（地基，先行）
Phase 1  删 typetype-server 后端（先提取 OTT catalog 到 RegistryAdapter，再删 leaderboard_adapter）
Phase 2  删 typetype-server QML/UI
Phase 3  删单实例 OTT 数据面 + legacy fallback（依赖 Phase 0 版本化；含前置验证门）
Phase 4  删配置迁移死代码（source_type/has_ranking/font_config/has_ranking DTO）
Phase 5  删孤儿脚本
Phase 6  example.org 哨兵移入迁移
Phase 7  测试收口 + 文档更新（新增本 ADR、更新 README/AGENTS/ARCHITECTURE/reference、删 api-endpoints.md）
```

Phase 0 与 Phase 1 可并行（都动 `container.py`/`bridge.py`，建议同批拉通）；Phase 3 依赖 Phase 0；Phase 7 最后。

### 风险

| 风险 | 等级 | 缓解 |
|:---|:---|:---|
| federation `_InstanceClient` 未完全覆盖 `OttTextProvider` | 高 | Phase 3 前置验证门，宁保留无 legacy 版也不盲目删 |
| 排行榜/成绩是用户可见功能 | 中 | 本地历史/字统计保留；ADR-012 明确后续；README/CHANGELOG 明示 |
| catalog 加载逻辑嵌在 leaderboard_adapter | 中 | Phase 1 先提取 OTT catalog 再删 |
| 迁移丢用户数据 | 中 | 只删 server/legacy 字段，保 `source_repos`/`wenlai`/`ai`/`ui`/本地历史；幂等测试双跑 |
| `text_sources` 误判为可删 | 低 | 已确认 `upload_text_adapter` 仍在写，收敛而非删除 |

## 待确认

1. Phase 3 前置验证门结论（federation 是否完整取代单实例数据面）。
2. 迁移是否需要在 `ui` 段之外，为 `ott` 段引入新的 RuntimeConfig 子 dataclass（建议新增 `OttConfig`，遵循 `WenlaiConfig`/`AiConfig` 模式）。
3. `docs/reference/api-endpoints.md` 直接删除 vs 归档到 `docs/history/`（server 文档，非三仓文档）。

> 更新检查与镜像下载机制（OTA）见独立 [ADR-014](./014-ota-update-check-and-mirror-download.md)。
