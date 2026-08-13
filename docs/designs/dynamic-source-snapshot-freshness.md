# 动态源的统一存储与载文机制：Content Snapshot + Freshness

- **日期**: 2026-08-13
- **状态**: 设计定稿，待实施
- **范围**: 客户端机制优先（EntrySnapshotStore / RefreshPolicy / SnapshotCatalogService / RefreshScheduler / QML 新鲜度表现 + 用户 per-source 刷新间隔覆盖）；协议 `refresh` 字段为后续上游同步项
- **关联**: ADR-013（三仓收敛）、ADR-009（OTT 只读协议边界）、ADR-010（联邦订阅）、AGENTS.md §8（OTT 只读协议/缓存层陷阱）

---

## 1. 背景与问题

### 1.1 现状

载文中心「开源文库」标签（`RepoEntriesPanel`）展示联邦聚合条目（`OttFederationProvider.list_all_entries()`）。条目来源分四类客户端：

| 客户端类型 | 内容动态性 | entry_id 生成 |
|:---|:---|:---|
| `_InstanceClient`（ott-instance） | 静态/低频（服务端或文件） | 服务端定义 |
| `_RuleClient`（ott-rule） | **每次请求随机 / 周期轮换** | `sha256(content)[:16]` |
| `_ScriptClient`（ott-script） | **每次请求随机** | 脚本返回 |
| `_BridgeClient`（ott-bridge） | **每日/周期轮换** | 服务端定义或内容 hash |

实测（`ott-source-hub` manifest）：一言（hitokoto）`v1.hitokoto.cn` 每次请求随机返回；今日诗词桥每日轮换；极速杯赛事文本轮换；zenquotes 脚本每次随机。

### 1.2 核心缺陷（已复现）

1. **选中载入失配**：`loadFederatedInlineEntry(authority, entry_id)` 在 bridge 侧**重新调用** `federation.get_entry()`，rule/script 源会**再次执行规则/脚本** → 抽到不同内容 → `entry_id` 失配 → `get_entry` 返回 None → 「无法加载条目」。当前仅靠 `_EntryCache`（内存 TTL 3600s）掩盖：缓存命中时稳定，过期/换进程即失败。已实测：`get_entry('2b96d8adb76257d4') → None`。
2. **物化结果不落盘**：列表展示的条目内容（rule/script/bridge 客户端保留完整 `content`）随内存缓存过期丢失，离线不可用。
3. **`update_freq` 字段废弃**：DTO/`ott_catalog.py`/`ott_normalization.py` 中已存在 `update_freq`（static/daily/weekly），但**零消费**——无存储、无调度、无 UI 表现。

### 1.3 需求

设计**统一**的存储与载文机制，适配所有更新频率的动态源（每次 / 每分钟 / 每小时 / 每天 / 每月 / 不固定频率），并提供统一的 UI-UX 表现。

---

## 2. 参考调研

### 2.1 Miniflux（Go RSS 阅读器）— 到期时间点模型

不按「频率」分类调度，每个源携带 `next_check_at` 时间戳，全局定时器只处理到期的源（`WithNextCheckExpired()` 批处理）。**频率不是 UI 概念，是条目自身的「到期时间」属性**。

### 2.2 NetNewsWire（Swift RSS 阅读器）— 全局策略 + 手动覆盖

全局可配置刷新间隔（手动/30min/1h/2h/4h/8h）+ 手动刷新 + 休眠恢复补偿；统一刷新进度显示。

### 2.3 本仓可复用能力

- `OttCachedFetcher`：TTL + stale-while-revalidate + 后台刷新 + 原子写（tmp+replace）+ 离线兜底缓存决策树
- `RepoManifestCache`：manifest TTL 缓存 + 后台刷新
- `_EntryCache`（联邦内）：rule/script 条目内存 TTL 缓存
- `TextSliceProgressStore`：按文本 hash 存进度（快照机制天然稳定）

---

## 3. 核心模型：Content Snapshot + Freshness

### 3.1 统一抽象

所有更新频率的源，其条目都是一份**已物化的内容快照**，携带**过期时间点** `next_refresh_at`：

| 频率 | 统一模型 |
|:---|:---|
| static（内置/本地） | `next_refresh_at = ∞`，不调度 |
| 每月/每天/每小时/每分钟 | `next_refresh_at = captured_at + interval_seconds`，到期自动刷新 |
| 每次随机 / 不固定 | `next_refresh_at = captured_at`（立即过期，快照仍可打），**仅手动刷新** |

### 3.2 两条铁律

1. **快照永远可打**：列表展示的物化内容落盘，选中载入直接从快照取，**绝不重新执行规则/脚本**。
2. **刷新只是换新**：刷新产生新快照并进入列表头部，旧快照保留（最近 N 条）可继续打/回看。

---

## 4. 组件设计

### 4.1 `RefreshPolicy`（integration 层，新文件 `src/backend/integration/refresh_policy.py`）

```python
@dataclass
class RefreshPolicy:
    mode: str              # "static" | "interval" | "on_demand"
    interval_seconds: int = 0

    def next_refresh_at(self, captured_at: float) -> float | None:
        """static → None（永不过期）；interval → captured_at + interval；
        on_demand → captured_at（立即过期）。"""
```

- **优先级链（三层逐级覆盖）**：用户覆盖（`source_refresh_overrides`，config.json） > manifest `source.refresh` 声明（未来协议，见 §8） > 客户端推断。
- 客户端推断（缺省）：`ott-instance → static`；`ott-rule / ott-script / ott-bridge → on_demand`。
- 解析入口 `RefreshPolicy.resolve(authority, source_dict)`：先查用户覆盖 → 再查 manifest 声明 → 最后推断。

### 4.1.1 用户覆盖：`RuntimeConfig.source_refresh_overrides`

用户可在订阅管理页手动调整某个源/规则（authority 级）的刷新间隔（per-source 覆盖，2026-08-13 决策）。

- 存储：`RuntimeConfig` 新增段 `source_refresh_overrides`：`dict[str, dict]`，key 为 `authority`，value 为 `{"mode": "interval"|"on_demand"|"static", "interval_seconds": int}`；遵循 AGENTS.md 约束（`@dataclass` 子配置 + `_from_dict`/`_to_dict`，RuntimeConfig 为唯一序列化者）。
- 操作入口：`runtime_config.set_source_refresh_override(authority, mode, interval_seconds)` / `clear_source_refresh_override(authority)`，**不直接操作字段**。
- 语义：`on_demand`（每次随机，立即过期仅手动）→ 用户可改成 `interval`（如每小时）使调度器自动换新；`static`（永不过期）→ 用户可改成 `interval` 定期刷新。删除覆盖 → 回退 manifest/推断。

### 4.2 `EntrySnapshotStore`（integration 层，新文件 `src/backend/integration/entry_snapshot_store.py`）

磁盘 JSON 快照存储，**纯存储无网络**：

```
registry_cache_dir()/snapshots/{authority_hash}/{entry_id}.json
```

```python
class EntrySnapshotStore:
    def save(self, entry: dict, captured_at: float, policy: RefreshPolicy) -> None
    def get(self, authority: str, entry_id: str) -> dict | None   # 含 freshness 元数据
    def list(self, authority: str) -> list[dict]                  # 按 captured_at 倒序
    def prune(self, authority: str, max_per_source: int = 5) -> None
    def due_for_refresh(self, now: float) -> list[tuple[str, str]]  # 调度用：仅 interval 模式到期
```

- 调度语义：`on_demand` 快照虽然 `next_refresh_at = captured_at`（UI 显示「可刷新/抽新」），但**调度器不得自动刷新**（否则每次 tick 都重新请求随机源，造成无限刷新循环）；`on_demand` 仅由用户手动触发。`static` 不参与调度。**只有 `interval` 模式的到期源进入调度**（`due_for_refresh` 只返回 interval 到期）。

- 快照文件内容：标准化 entry（沿用 `normalize_summary` 字段形状）+ `content` + `captured_at` + `refresh_policy` + `next_refresh_at`。
- 原子写：tmp + `Path.replace`（复用 `OttCachedFetcher.write_cache` 模式）。
- 损坏/读取失败 → 静默返回 None（视为无快照），不阻塞。
- `authority_hash = sha256(authority)[:12]`（与 `_instance_cache_dir` 同风格）。

### 4.3 `SnapshotCatalogService`（application 层，新文件 `src/backend/application/services/snapshot_catalog_service.py`）

编排层（符合 AGENTS.md「有编排逻辑 → UseCase/Service」）：

```python
class SnapshotCatalogService:
    def __init__(self, federation, store, policy_resolver, max_per_source: int = 5): ...

    def refresh_and_list_all(self) -> list[dict]:
        """物化 → 逐条 save → prune → 返回带 freshness 元数据的摘要列表。"""
        entries = self._federation.list_all_entries()
        for e in entries:
            policy = self._policy_resolver(e)
            self._store.save(e, captured_at=now, policy=policy)
            self._store.prune(authority, max_per_source)
        return [self._decorate(e) for e in entries]

    def load_entry(self, authority: str, entry_id: str) -> dict | None:
        """快照命中直接返回（不重抽）；miss → federation.get_entry 兜底。"""
        snap = self._store.get(authority, entry_id)
        if snap is not None:
            return snap
        return self._federation.get_entry(authority, entry_id)

    def refresh_source(self, authority: str) -> None: ...      # 单源强制刷新（random 换新）

    def scheduled_tick(self) -> None: ...                      # 扫描到期，后台刷新（async_executor）
```

- `load_entry` 是修复「选中载入失配」的关键路径：**不重新执行规则/脚本**。
- `decorate` 追加 freshness：`fresh / stale / on_demand`、`captured_at`、`next_refresh_at`、`last_fetched_relative`。

### 4.4 `RefreshScheduler`（integration 层，新文件 `src/backend/integration/refresh_scheduler.py`）

常驻轻量调度（借鉴 Miniflux 到期模型）：

- `QTimer` 60s tick → `SnapshotCatalogService.scheduled_tick()` → 扫描 `interval` 模式到期的源（`due_for_refresh`），后台刷新（复用 `async_executor`，去重防并发）。
- **只自动刷新 `interval` 模式**；`on_demand` 仅用户手动刷新；`static` 不调度。
- 启动时机：应用启动、载文中心激活（`onActiveChanged`）、列表可见时触发一次立即扫描。
- 刷新失败 → 保留旧快照 + 标记 stale，可继续打。

### 4.5 Presentation 层

- `RegistryAdapter`：新增转发 `refreshFederatedSource(authority)` 等；**不直持 Store**（Bridge 禁止直持 integration 对象）。
- `Bridge`：`loadFederatedEntries` 走 `refresh_and_list_all()`；`loadFederatedInlineEntry` 走 `load_entry()`（快照优先）；新增 `refreshFederatedSource` slot。
- `container.py`：装配 Store / Policy / Service / Scheduler（复用现有 `manifest_async_executor`）。

### 4.6 QML 层

**`RepoEntriesPanel` 卡片增强**（所有频率统一表现）：

| 元素 | 内容 |
|:---|:---|
| 新鲜度徽章 | 最新（主题色）/ 可刷新（黄色）/ 随机源（「抽新」按钮） |
| 上次抓取 | 相对时间：「3 分钟前」「昨天」（helper 格式化） |
| 下次自动刷新 | 「23 分钟后」「每天」「手动」 |
| 刷新动作 | 全局刷新（现有）+ 单卡片刷新（random 源 = 换新一篇） |
| 载入 | 打当前快照；过期快照**仍可载入** |

- `TextSourceBehaviors.js`：新增相对时间格式化 helper；`progressKeyAndId` 不变（快照下 `ott:{authority}:{entry_id}@{revision_id}` 天然稳定）。
- 单卡片刷新 loading 态去重（防连点）。

**`ReposManagementPage` 每源「刷新间隔」设置**（per-source 覆盖入口）：

- 每条订阅摘要的源列表旁提供刷新间隔入口：下拉（手动/随机 / 每小时 / 每天 / 每周 / 每月 / 不刷新）+ 自定义秒数输入。
- 写入 `runtime_config.set_source_refresh_override(authority, mode, interval_seconds)`；覆盖生效后该源 `RefreshPolicy` 立即按新策略计算（下次 `next_refresh_at` 以当前时间重新锚定）。
- 「重置为默认」清除覆盖，回退 manifest/推断。

---

## 5. 数据流

```
列表加载:  refresh_and_list_all()
  → federation 物化 → 每条 store.save(captured_at=now, policy) → prune(每源5)
  → 返回快照摘要 + freshness → RepoEntriesPanel 渲染

选中载入:  loadFederatedInlineEntry(authority, entry_id)
  → store.get(authority, entry_id) 命中 → 直接返回 ✅ 不重抽 → 永不失配
  → miss（极端）→ federation.get_entry 兜底

自动刷新:  RefreshScheduler.tick()
  → 扫描 interval 模式到期源（on_demand 不自动刷新）→ 后台刷新
  → 新快照入库 + prune → 旧快照保留（最近 N 条，可回看/可继续打）
```

---

## 6. 错误处理

| 场景 | 行为 |
|:---|:---|
| 快照写失败 | 静默降级，列表仍用内存结果 |
| 快照读失败/损坏 | 返回 None，视为无快照 |
| 刷新失败 | 保留旧快照 + stale 标记，可继续打 |
| 离线 | 快照即离线兜底（列表也能离线显示，强于现状） |
| 单卡片连点刷新 | loading 态去重 |

---

## 7. 测试策略

- `EntrySnapshotStore`：save/get/list/prune/原子写/损坏文件兜底/authority_hash 布局
- `RefreshPolicy`：各模式 `next_refresh_at` 计算、优先级链（用户覆盖 > manifest 声明 > 推断）、`resolve` 无覆盖回退推断
- `RuntimeConfig.source_refresh_overrides`：`set/clear` 写读、v1→v2 迁移缺省空段、`_from_dict` 类型容错
- `SnapshotCatalogService`：**mock federation 断言 `load_entry` 零 fetch**（失配修复回归）；`refresh_and_list_all` 写快照+prune 保留 N；`refresh_source` 换新；覆盖生效后 `next_refresh_at` 重新锚定
- `RefreshScheduler`：到期扫描、去重、后台执行
- QML：新鲜度徽章渲染 + 刷新间隔下拉（复用 `test_qml_pages.py` 框架）

---

## 8. 实施边界与后续

**本次实施（客户端机制优先）**：
- §4 全部组件（含 §4.1.1 用户 per-source 覆盖）+ §5 数据流 + §6 错误处理 + §7 测试
- 策略推断内置（instance→static、rule/script/bridge→on_demand），用户覆盖（`source_refresh_overrides`）优先
- 快照保留 N 默认 5（可配置）

**后续（不在本次）**：
- 协议 `source.refresh` 声明（`{"mode": "interval", "interval_seconds": 86400}` / `"on_demand"` / `"static"`）——open-typing-texts 仓同步项，客户端读取声明，位于优先级链中段（用户覆盖之下）
- 快照 GC / 清理设置页 UI
- 旧 `update_freq` 字段的迁移/删除决策

**不动**：6 tab 载文中心结构、进度键格式、`OttClient`/`OttCachedFetcher`/`OttFederationProvider` 现有接口。

---

## 9. 参考

- Miniflux scheduler：`internal/cli/scheduler.go`（`WithNextCheckExpired` 批处理）— Apache-2.0
- NetNewsWire `RefreshInterval.swift` / `AccountRefreshTimer.swift`（全局间隔 + 手动 + 休眠补偿）— BSD
- 本仓：`OttCachedFetcher`（TTL/SWRA/原子写）、`_EntryCache`（内存 TTL）、`update_freq`（废弃字段）、`TextSliceProgressStore`（文本 hash 进度）
