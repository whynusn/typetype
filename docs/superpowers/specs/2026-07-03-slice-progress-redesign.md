# 分片进度系统重新设计

日期: 2026-07-03

## 1. 问题分析

### 1.1 现状

进度是一个扁平的 JSON entry，以 text source 的 hash 为 key。

```json
"sha256(__local_article__:前五百-ed5f6defa079)": {
    "current_slice": 3,
    "total_slices": 50,
    "slice_pass_counts": [2, 1, 0, 0, ...],
    "slice_size": 10,
    "slice_stats": [...],
    "slice_metrics": [...],
    "advance_mode": "sequential",
    "shuffle_seed": null,
}
```

每次导航（next/prev/random）结束后都调用 `_update_progress_current_slice()` （[bridge.py:1768-1767]），把 `current_slice` 覆盖为当前切片的索引。这是核心问题。

### 1.2 三个缺陷

**缺陷 A：`current_slice` 语义混乱**

同一个字段同时承担：
- **"还能从哪继续"**（顺序进度恢复点）— 用户下次回来应该继续的地方
- **"当前展示在哪"**（浏览位置）— 随机跳转后的临时位置

两者混用。点击"随机段"后 `_update_progress_current_slice`（[bridge.py:1782]）把 `current_slice` 覆盖为随机段索引，顺序进度丢失。

**缺陷 B：手动切换不保存**

`_save_current_slice_if_needed`（[bridge.py:1734]）检查 `_last_slice_stats` 是否为空。`_last_slice_stats` 仅在 `_check_typing_complete`（[typing_adapter.py:201]）中设置，即用户**打完当前片所有字**时。手动按下一片但没打完 → 不触发保存 → 进度条目根本不存在。

**缺陷 C：覆盖旧版进度 key**

自定义文本（custom_text）的进度 key 基于 `sha256(text)`。如果同一文本在不同版本间因换行/空格处理不同而产生不同 hash，旧 key 就找不到了。

### 1.3 本次设计只解决缺陷 A

缺陷 B 已在上一轮修复中解决（加了 `clear_last_slice_stats` 和恢复逻辑）。缺陷 C 涉及不同问题，暂不处理。

## 2. 设计目标

1. 随机跳转不应覆盖用户的顺序恢复点
2. 恢复点应有意义：告诉用户"你还需要练哪里"
3. 适应两种推进模式（顺序首尾相连 / 随机无限选段）
4. 改动最小：尽量不新增字段、不改变现有数据格式

## 3. 核心方案："resume = 第一个未达标的切片"

### 3.1 基本原理

放弃用 `current_slice` 字段作为恢复点。改用**实时计算**：

```python
def _compute_resume_slice(
    pass_counts: list[int], 
    pass_count_min: int,
    fallback: int
) -> int:
    """返回第一个未达标的切片索引。全部达标时回退到 fallback。"""
    for i, count in enumerate(pass_counts, start=1):
        if count < pass_count_min:
            return i
    return fallback
```

> `pass_count_min` 是"达标所需最低次数"（threshold），比如设为 3 表示每片至少达标 3 次。`count < pass_count_min` 即"还没达到要求"。命名读起来确实有歧义但系历史遗留，不改。

**不需要新增字段**。`slice_pass_counts` 和 `pass_count_min` 已经存在。

### 3.2 推演

设 `pass_count_min=1`，50片：

| 操作 | slice_pass_counts | resume |
|:---|:---|:---|
| 初始 | `[0]*50` | 1 |
| 顺序打完 1,2,3 | `[1,1,1,0,0,...]` | **4** |
| 随机跳到 37，打完达标 | `[1,1,1,0,...,1,...]` | **4** ← 不受影响 |
| 从 4 继续，打到 10 | `[1,1,1,1,...,1,0,...]` | **11** |
| 全部达标 | `[≥1]*50` | `fallback`（当前段索引） |
| 全达标后再回到 slice 1 打了一次 | `[2,1,1,...]` | 仍为 `fallback`（已全达标） |

`pass_count_min=3` 的场景：

| 操作 | pass_counts | resume |
|:---|:---|:---|
| 顺序打完 1(3次), 2(2次) | `[3,2,0,...]` | **2**（还差1次） |
| 随机跳 37，打完 1次 | `[3,2,0,...,1,...]` | **2** |

**无论怎么跳，resume 永远指向"还没达标的第一个片"。**

### 3.3 适配两种推进模式

**顺序推进（首尾相连，无限循环）**：
- resume 指向第一个未达标的片（按索引顺序）
- 全部达标后回退到 `current_slice`

**随机推进（advance_mode="random"）**：
- 本来就没有顺序概念，resume 是"薄弱片聚合"的自然结果
- 每次随机跳转打到未达标的片达了标，resume 自动推进

### 3.4 初始化全未达标 vs 部分未达标

- 新文本首次进入分片模式：`_slice_pass_counts = [0] * total`（[session_context.py:274]），resume = 1
- 恢复已有进度：`_restore_pending_progress`（[bridge.py:531]）从 JSON 恢复 `slice_pass_counts`，resume = 根据恢复后的 counts 计算

## 4. 变更清单

### 4.1 新增接口（不暴露为 Slot）

**文件**：`src/backend/presentation/bridge.py`

```python
@staticmethod
def _compute_resume_slice(
    pass_counts: list[int], 
    pass_count_min: int, 
    fallback: int
) -> int:
    for i, count in enumerate(pass_counts, start=1):
        if count < pass_count_min:
            return i
    return fallback
```

（或放在 `session_context.py` 中，视调用距离定。）

### 4.2 变更 `_restore_pending_progress`

**文件**：`bridge.py`，方法 `_restore_pending_progress`（[line 531]）

在当前逻辑末尾，恢复完 `slice_pass_counts` 后，**计算 resume_slice 并注入到 `_pending_restored_progress`**：

```python
# 在方法末尾，self._pending_restored_progress = None 之前
rp["resume_slice"] = self._compute_resume_slice(
    ctx._slice_pass_counts, ctx._pass_count_min,
    ctx.slice_index  # fallback
)
```

这样后续 setup 方法可以直接读取 `_pending_restored_progress["resume_slice"]`。

### 4.3 变更 `setupLocalArticle` 的恢复起点

**文件**：`bridge.py`，方法 `setupLocalArticle`（[line 1145-1149]）

将：
```python
if self._pending_restored_progress:
    saved_slice = self._pending_restored_progress.get("current_slice", 1)
```
改为：
```python
if self._pending_restored_progress:
    saved_slice = self._pending_restored_progress.get("resume_slice")
    if saved_slice is None:
        saved_slice = self._pending_restored_progress.get("current_slice", 1)
```

同理变更 `setupTrainer`、`setupSliceMode`（custom_text/jisubei）中的恢复起点。

### 4.4 变更 restore dialog 显示

**文件**：`SliceProgressRestoreDialog.qml`（[line 63]）

当前显示 `"第 %1 / %2 段"` 使用 `saved_slice`。这个值是 `current_slice`，来自 `getSliceProgressInfo`（[bridge.py:1875-1904]）。

在 `getSliceProgressInfo` 返回的 JSON 中增加 `resume_slice` 字段：

```python
info = {
    "saved_slice": progress.get("current_slice", 1),
    "resume_slice": self._compute_resume_slice(
        pass_counts, pass_count_min, progress.get("current_slice", 1)
    ),
    ...
}
```

Dialog 显示时，默认显示 resume_slice，并在下方小字标注 "当前浏览位置"（current_slice）。

### 4.5 每次 `collectSliceResult` 后更新 resume 字段

**文件**：`bridge.py`，方法 `collectSliceResult`（[line 1650]）

保存进度时，当前已经保存了 `slice_pass_counts` 和 `metrics.pass_count_min`。每次从 JSON 读取数据时计算 resume，所以不需要额外处理——只要 pass_counts 保存正确，restore 时就能算出正确的 resume。

### 4.6 不变的部分

| 组件 | 不变原因 |
|:---|:---|
| `_update_progress_current_slice` 的调用位置 | 仍更新 `current_slice` 用于显示"当前浏览位置" |
| `text_slice_progress_store.py` | 不新增字段，不修改 JSON 结构 |
| `collectSliceResult` 的进度 dict | 已包含 `slice_pass_counts` + `metrics.pass_count_min` |
| QML 的 `hasSliceProgress` / 按钮可见性 | 逻辑不变，只是恢复点的语义变了 |

## 5. 恢复对话框的设计（改动部分）

```
┌──────────────────────────────┐
│  发现历史进度                  │
│                              │
│  文本: 前五百                 │
│                              │
│  顺序进度: 第 6/50 段  ← resume_slice（默认选中）
│  ████████░░░░░░░░░░░░░░░     │
│                              │
│  (当前浏览: 第 37/50 段)      │  ← 灰字显示 current_slice
│                              │
│  [取消] [重新开始] [继续]     │
└──────────────────────────────┘
```

点击"继续"：恢复时使用 `resume_slice` 作为起点。用户仍可按"随机段"去任意位置。

点击"取消"：`restoreRejected`，不走恢复逻辑。

点击"重新开始"：`applySliceProgressRestore(..., false)` 删除进度条目。

## 6. 边界场景

### 6.1 全部达标，无限循环

`pass_counts = [3,3,3,...], resume = fallback = current_slice`

用户全部达标后还在打（无限循环模式），恢复时回到当前浏览位置。合理——用户已经不需要恢复点了。

### 6.2 降级场景（已有 JSON 无 resume_slice）

`_pending_restored_progress.get("resume_slice")` 返回 None → 回退到 `current_slice`。与当前行为一致。**向前兼容。**

### 6.3 分片全部 0 达标

新文本，`pass_counts = [0,0,...]` → resume = 1。正确。

### 6.4 跳着达标（片 1,3,5 达标，2,4 未达标）

`pass_counts = [1,0,1,0,1,...], pass_count_min = 1` → resume = **2**（第一个未达标）。正确——应该继续从 2 练。

### 6.5 用户只打了随机段，从未顺序推进

假设 50 片，用户只打到了 37（随机），达标 1 次：
`pass_counts[36] = 1, 其余 = 0` → resume = **1**。正确——从第一片开始按顺序练。

### 6.6 用户从 resume 开始顺序打，但跳着打了前几片

resume = 2（片 1 未达标），用户手动跳到片 1 打完达标：
`pass_counts[0] = 1` → resume 自动推进到 3（片 2 没达标但 reseek 是从头扫描）。正确。

## 7. 不解决的场景

- **同一文本的多个进度分支**：不在本次范围内。用户需要分支时用"重新开始"。
- **旧格式 key 到新格式 key 的迁移**：`_find_progress` 已有 title scan fallback 处理。
- **进度冲突（多设备）**：单用户单设备场景，不需要冲突检测。

## 8. 验证场景

### S1: 顺序推进后恢复（Happy path）
1. 打开 `前五百`，打达标片 1,2,3
2. 推进到片 4，关掉应用
3. 重新打开 → 恢复弹窗，恢复起点 = 4

### S2: 随机跳转不干扰恢复点
1. 顺序打到片 3，随机跳到片 37
2. 关掉应用
3. 重新打开 → 恢复弹窗显示 `resume=4, current=37`
4. 点击"继续" → 从片 4 开始

### S3: 全部达标后循环
1. 所有 50 片都达标至少 1 次
2. 当前在片 22
3. 关掉应用
4. 重新打开 → 恢复起点 = 22（fallback）

### S4: 降级兼容（旧进度条目无 resume_slice）
1. 用旧版本创造一条进度（只有 `current_slice`，无 `resume_slice` 概念）
2. 升级到新版本
3. 恢复弹窗显示 `current_slice`（回退行为）

每项验证时检查：
- `TYPETYPE_DEBUG=1` 日志中的 `[_find_progress]` 和 `[prepareSliceProgressRestore]` 输出
- JSON 文件内容确认 `current_slice` 未被随机跳转污染
- 恢复后的实际切片内容是 resume_slice 对应的文本
