# TypeType 性能与内存问题深度分析（待解决）

**日期**: 2026-04-26  
**分析方式**: 静态代码审计（含调用链核对）  
**状态**: 待优化（未实施修复）

---

## 结论摘要（按优先级）

> 本文已按「superpowers:verification-before-completion」思路补充：
> 1) 结论确定性（Definite/Likely）
> 2) 误报排除（False-positive checks）
> 3) 可量化验收标准（KPI）

### P0（高优先级，Definite）

1. **排行榜链路存在级联请求 + 过量取数 + 重渲染叠加**
2. **长文本跟打路径存在线性内存占用与高频逐字符格式更新**

### P1（中高优先级，Definite/Likely）

3. **后台任务缺少去重/节流/取消，易出现“结果被丢弃但工作已完成”的抖动浪费**
4. **单实例页面策略放大了模型与历史状态的常驻内存问题**

### P2（中优先级，Likely）

5. **排行榜日期标准化与调试输出存在可避免的 CPU/日志 IO 开销**

---

## 证据与分析

## A. 确定性分级总览（来自代码证据 + Oracle 复核）

| 问题 | 级别 | 确定性 | 说明 |
|:--- |:--- |:--- |:---|
| 排行榜页面激活触发级联请求（目录→列表→首条排行） | P0 | Definite | 调用链明确且默认触发，无需运行时假设 |
| 排行榜加载前额外获取完整文本详情（含 content） | P0 | Definite | Worker 逻辑固定为先拉 text detail 再拉 leaderboard |
| 长文本输入路径高频逐字符处理/着色 | P0 | Definite | `onTextChanged` + Python 处理 + QTextCursor 更新链路明确 |
| 本地 text_id 回查每次新建 daemon thread | P1 | Definite | 每次调用都 `threading.Thread(...).start()`，无去重/限流 |
| WeakChars 查询触发过密（排序/权重即时 reload） | P1 | Likely | 触发路径明确；实际损耗大小需 profile 量化 |
| 单实例页面放大模型常驻问题 | P1 | Likely | 架构策略 + 页面模型持有明确；峰值需运行时测 |
| 排行榜日期标准化日志过密 | P2 | Definite | 记录级 `log_info` 在每次请求中运行 |

## 1) 排行榜链路（P0）

### 1.1 页面激活时强制刷新目录，触发后续级联加载

- `src/qml/pages/TextLeaderboardPage.qml:906-909`：`onActiveChanged` 每次 active 都 `appBridge.refreshCatalog()`。
- `src/backend/presentation/adapters/leaderboard_adapter.py:151-156`：`refreshCatalog()` 先清缓存再 `loadCatalog()`。
- `src/qml/pages/TextLeaderboardPage.qml:34-43`：`syncSourceOptions()` 将 `currentIndex = 0`。
- `src/qml/pages/TextLeaderboardPage.qml:111-122`：`onCurrentIndexChanged` 触发 `loadTextList(key)`。
- `src/qml/pages/TextLeaderboardPage.qml:875-880`：文本列表加载完成后自动选中第一条并立刻 `loadLeaderboardByTextId()`。

**影响**：进入页面即发生“目录 → 列表 → 排行榜”级联请求，即使用户尚未进行任何选择。

**False-positive check**：
- 虽然 `main.py:268-269` 启动时调用 `bridge.loadCatalog()`，但页面激活走的是 `refreshCatalog()`（清缓存后重载），因此预加载不会消除该级联。

### 1.2 拉排行榜前额外取完整文本详情（含 content）

- `src/backend/workers/leaderboard_worker.py:68-75`：`_fetch_by_text_id()` 先 `get_text_by_id()` 再 `get_leaderboard()`。
- `src/backend/workers/leaderboard_worker.py:82-86`：返回 `text_info` 包含 `content`。
- `src/backend/integration/leaderboard_fetcher.py:105-126`：`get_text_by_id()` 获取完整文本详情。

**影响**：排行榜页主视图只需标题/统计，但链路额外拉取完整文本内容，扩大网络与内存压力。

**False-positive check**：
- 当前并不存在“按需拉 content”分支；该额外请求属于默认必经路径，不是偶发行为。

### 1.3 文本列表无分页，页面侧持有完整数组与模型

- `src/backend/integration/leaderboard_fetcher.py:82-103`：`get_texts_by_source()` 返回来源下全部文本列表。
- `src/qml/pages/TextLeaderboardPage.qml:19`：`leaderboardRecords` 常驻数组。
- `src/qml/pages/TextLeaderboardPage.qml:24-31`：`textListModel` / `sourceListModel` 常驻 `ListModel`。

**影响**：当来源文本数量大时，QML JS 堆与 delegate 创建成本同步放大。

---

## 2) 跟打主链路（P0）

### 2.1 明确的 O(n) 内存结构（需注意规模效应）

- `src/backend/domain/services/typing_service.py:149-155`：`set_total_chars(total)` 分配 `wrong_char_prefix_sum = [0 for _ in range(total)]`。
- `src/backend/application/session_context.py:162-165`：分片模式按片创建字符串列表 `self._slices`，对全文做切片复制。

**影响**：文本越长，内存线性上升；并且是进入会话即分配/复制，不是按需增量。

**边界说明（避免过度解读）**：
- 对常规短文（几千字）该项可能不是主瓶颈；但在“长文 + 长时会话 + 富文本着色”叠加场景下，会放大峰值内存与 GC 压力。

### 2.2 高频事件中逐字符处理与格式更新

- `src/qml/typing/LowerPane.qml:118-170`：每次 `onTextChanged` 都触发 bridge 调用与增删处理。
- `src/backend/domain/services/typing_service.py:223-242`：逐字符更新 prefix_sum 与字符统计累积。
- `src/backend/presentation/adapters/typing_adapter.py:297-314`：对每个更新字符调用 `_color_text`（`QTextCursor.setCharFormat`）。

**影响**：输入高频时产生“QML 事件 + Python 逻辑 + QTextDocument 格式写入”三重热路径，长文本下更明显。

**False-positive check**：
- 此路径是业务必需，不代表“必须删除”；问题在于缺少节流/批处理策略，需以 profiler 判断最优改法。

---

## 3) 后台任务与线程抖动（P1）

### 3.1 本地 text_id 回查每次新建原生线程

- `src/backend/presentation/adapters/text_adapter.py:75-92`：`threading.Thread(..., daemon=True).start()`，无队列/复用/去重。

**影响**：频繁触发载文/回查时易产生短生命周期线程抖动；即使结果被覆盖，工作仍已执行。

**补充风险**：
- 缺少 in-flight 复用与取消，属于“结果可丢弃但成本已支付”的典型路径。

### 3.2 薄弱字查询每次请求都新建 Worker

- `src/backend/presentation/adapters/char_stats_adapter.py:20-38`：`loadWeakChars()` 每次启动 `WeakCharsQueryWorker`。
- `src/qml/pages/WeakCharsPage.qml:62-69, 90, 102, 114`：排序与权重变更立即 reload。

**影响**：用户快速切换排序/权重会触发连续查询，缺少 debounce/coalescing。

**False-positive check**：
- 单次查询可能很快，但连发请求导致 UI 模型重复清空/追加，属于可避免开销。

### 3.3 隐藏页面仍可能响应 typingEnded（缺 active 守卫）

- `src/qml/pages/WeakCharsPage.qml:227-238`：`Connections` 中 `onTypingEnded` 无 `enabled: weakCharsPage.active` 守卫。

**影响**：非激活页面也会被全局打字结束信号触发刷新，增加无效后台工作。

---

## 4) 生命周期与内存常驻（P1）

- `docs/ARCHITECTURE.md:570`：NavigationView 为**单实例页面缓存复用**。
- `src/qml/pages/TypingPage.qml:177` + `src/qml/typing/HistoryArea.qml:65`（见既有分析）历史记录持续插入且无显式裁剪策略。
- `src/qml/pages/TextLeaderboardPage.qml:19,24`：排行榜与文本列表模型为页面级常驻对象。

**影响**：页面不销毁时，模型/历史/缓存更容易从“短时占用”演化为“长时驻留”。

**False-positive check**：
- 单实例本身不是 bug；问题在于“常驻策略 + 无上限/缺释放”的组合效应。

---

## 5) 日志与数据标准化开销（P2）

- `src/backend/integration/leaderboard_fetcher.py:181-195`：每次排行榜响应都输出记录级 `log_info`。
- `src/qml/pages/TextLeaderboardPage.qml:731-734`：delegate `Component.onCompleted` 调试输出。

**影响**：大量排行记录时，日志字符串构造与 IO 会成为可见噪声开销。

---

## 风险归因（不是单点泄漏，而是叠加效应）

当前更像是**取数策略偏重 + 高频渲染路径 + 生命周期常驻**叠加，而非单一“内存泄漏点”。

---

## 建议的修复顺序（待实施）

1. **先改排行榜链路（P0）**
   - 避免进入页面自动拉首条排行榜。
   - 排行榜接口优先只取必要字段；文本详情按需加载（如用户显式查看全文时再取）。
   - 文本列表引入分页/懒加载。

2. **再改输入热路径（P0）**
   - 评估逐字符着色频率（批量更新或窗口化更新）。
   - 长文本模式下优化 `wrong_char_prefix_sum` 与分片存储策略（避免一次性全量结构）。

3. **压制后台抖动（P1）**
   - text_id 回查改为受控执行器（队列/去重/并发上限/可取消）。
   - WeakChars 查询增加 debounce + in-flight 合并。
   - 给 WeakCharsPage 的 `typingEnded` 连接加 `active` 守卫。

4. **治理常驻内存（P1）**
   - 历史记录上限（例如仅保留最近 N 条）。
   - 隐藏页必要时释放大模型数据（或做轻量缓存）。

5. **最后清理日志噪声（P2）**
   - 将记录级日志降级到 debug 且加采样/开关。

---

## 分阶段执行清单（可直接立项）

### Phase 1（1-2 天，优先止损）

1. 排行榜页取消“激活即强制刷新目录”的默认行为（改为缓存优先 + 显式刷新按钮触发）。
2. 文本列表加载后取消“自动拉首条排行榜”，改为用户显式选择触发。
3. 弱字符页 `typingEnded` 连接增加 `active` 守卫。
4. 日期标准化记录级日志改为 debug 级并加开关。

### Phase 2（2-4 天，结构优化）

1. `text_id` 回查改为受控执行器（并发上限、去重、可取消或 latest-only 策略）。
2. WeakChars 查询加 debounce 与 in-flight 合并。
3. 历史记录加上限策略（例如保留最近 N 条）。

### Phase 3（按 profile 决策）

1. 输入热路径：评估逐字符着色的批处理/窗口化。
2. 长文本模式：评估分片数据结构的延迟构建或轻量表示。

---

## 验证计划（修复前后都应执行）

1. QML Profiler：验证页面切换与排行榜加载的 delegate 创建量、绑定重算、帧耗时。  
2. Python 侧采样：对排行榜加载、onTextChanged 热路径做 CPU 采样。  
3. RSS/堆监控：分别在“长文本跟打 10 分钟”“多次切换排行榜来源”场景下测峰值和回落。  
4. 网络请求计数：统计进入排行榜页一次产生的请求数，作为优化 KPI。  

### KPI（验收阈值建议）

- **KPI-1 请求数**：首次进入 `TextLeaderboardPage` 的默认请求数下降到 <= 2（当前为级联 3+）。
- **KPI-2 响应延迟**：排行榜页面首屏可交互时间（TTI）较基线下降 >= 30%。
- **KPI-3 线程抖动**：快速切换来源 10 次时，新增原生线程峰值显著下降（目标：受控在固定上限内）。
- **KPI-4 内存驻留**：长文本连续练习 10 分钟后，RSS 峰值与回落曲线较基线改善（至少峰值下降或回落更快）。
- **KPI-5 无效刷新**：WeakCharsPage 非激活状态下不再响应 `typingEnded` 触发查询。

---

## 已知边界

- 本文为静态分析，未直接给出运行期 flamegraph/RSS 数值。  
- 具体收益需以 profile 数据确认，但上述问题均有明确代码证据与触发路径。

---

## 完成定义（Definition of Done, for this document）

- [x] 问题按优先级分层（P0/P1/P2）
- [x] 每项问题有代码级证据（file:line）
- [x] 增加确定性分级（Definite/Likely）
- [x] 增加误报排除说明（False-positive checks）
- [x] 给出可执行修复顺序与分阶段计划
- [x] 给出可量化验证方案与 KPI
