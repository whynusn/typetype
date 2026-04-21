# 载文（分片跟打）功能设计

## 1. 背景与目标

连贯文本通常数百字，不利于用户短时间内对某几个字进行大量练习。"载文"功能允许用户将选定文本按指定字数分片，逐片跟打，并根据预设条件自动推进。

**核心约束：** 分片模式下所有成绩仅本地记录，不提交服务端。服务端只记录未分片的全文成绩，保证排行榜公平性。

## 2. 架构方案

**Bridge 集中管理载文状态** + QML 轻量层。Bridge 持有分片列表、当前索引、重打条件；typingEnded 时 QML 判断 slice mode 分支，Bridge 执行推进逻辑。

理由：Bridge 已是信号枢纽，重打条件需读 SessionStat，在 Bridge 侧最方便。QML 侧改动最小——只需在 `onTypingEnded` 中加一个条件分支。

## 3. UI 设计

### 3.1 ToolLine 改动

"载文"按钮：点击打开载文 Dialog（替换直接随机载文）。"剪贴板载文"按钮保留作为快捷操作。

### 3.2 载文 Dialog（SliceConfigDialog.qml）

```
┌──────────────────────────────────────────────────┐
│  载文设置                                [×]      │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌─ 文本内容 ────────────────────────────────┐   │
│  │  [TextArea] 输入/粘贴文本，或从下方选择     │   │
│  │  ...                                      │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  ┌─ 从文本库选择 ────────────────────────────┐   │
│  │  来源: [ComboBox 本地示例/前五百/自定义…]  │   │
│  │  ┌─────────────────────────────────────┐  │   │
│  │  │ 《岳阳楼记》              368字     │  │   │
│  │  │ 《出师表》                633字     │  │   │
│  │  │ ...                                │  │   │
│  │  └─────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  ┌─ 分片设置 ────────────────────────────────┐   │
│  │  每片字数: [ComboBox: 20/30/50/100]       │   │
│  │  ☐ 全文载入（不分片）                      │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  ┌─ 重打条件 ────────────────────────────────┐   │
│  │  ☑ 开启重打条件                           │   │
│  │  当 [指标:速度] [比较符:<] [阈值:60] 时重打│   │
│  │  ☐ 重打时乱序                             │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│             [ 取消 ]      [ 开始载文 ]           │
└──────────────────────────────────────────────────┘
```

**交互逻辑：**
- 点击文本列表项 → 内容填充到上方 TextArea（可预览/编辑）
- 来源切换 → 刷新文本列表（见下方本地/网络加载策略）
- TextArea 有内容 → "开始载文"可用；否则禁用

**重打条件选项：**
- 指标：速度(CPM) / 准确率(%) / 错字数(个)
- 比较符：< / ≤ / ≥ / >
- 阈值：ComboBox 离散值（速度 20-300，准确率 50-100，错字数 0-50）

### 3.3 底部状态栏（TypingPage）

载文模式激活时，在 HistoryArea 上方显示条件状态条：

```
┌──────────────────────────────────────────────────┐
│  📄 载文模式: 第 3/5 片  │  上一片: 85CPM 98% ✓  │
└──────────────────────────────────────────────────┘
```

通过 `sliceStatusChanged` 信号更新内容，退出载文模式时隐藏。

### 3.4 EndDialog 改动

载文模式下所有片打完后弹出综合成绩框，显示聚合数据：

```
┌──────────────────────────────────────────────────┐
│  打字结束 — 综合成绩（5片）              [×]     │
├──────────────────────────────────────────────────┤
│  速度: 85 CPM  击键: 4.2 KPS  码长: 2.3         │
│  准确率: 96.5%  错字: 12  回改: 3               │
│  总字数: 150  总用时: 186.5s                     │
│  （分片模式成绩不提交排行榜）                     │
├──────────────────────────────────────────────────┤
│  [ 确定 ]                          [ 复制成绩 ]  │
└──────────────────────────────────────────────────┘
```

## 4. 文本来源

Dialog 中的文本来源下拉框直接使用 config.json 中已有的来源配置（与 ToolLine 的 sourceSelector 共享同一套来源列表）。无需修改 config。

| 来源 | 加载方式 | 网络依赖 | text_id |
|---|---|---|---|
| 有 local_path 的源（本地示例/前五百/…） | 读取 config 中 local_path 对应的文件 | ❌ 无 | None（异步回查） |
| 无 local_path 的源（极速杯等） | 服务端 API `loadTextList(source_key)` | ✅ 需要 | 按原文 ID |

### 4.1 Dialog 文本选择交互

Dialog 的 ComboBox 展示已有来源，ListView 列出该来源下的文本：

- **本地源**：每个来源对应单个文件，ListView 显示 1 条记录（文件名 + 字数）。选中后读取文件内容填入 TextArea。
- **远程源**：走现有 `loadTextList` API，ListView 显示多条记录。选中后通过 `getTextContentById` 异步获取内容填入 TextArea。

用户在 TextArea 中可以预览和编辑内容。

### 4.2 Bridge Slot：获取文本列表

```python
@Slot(str, result="QVariantList")
def getTextListForSlice(self, source_key: str) -> list[dict]:
    """为载文 Dialog 返回某来源的文本列表。
    本地源：直接调用 list_local_texts() 或读取单文件，同步返回。
    远程源：走现有 TextListWorker 异步链路，通过 textListLoaded 信号返回。
    """
```

### 4.3 远程源文本内容获取

用户从远程源（如极速杯）选择文本后，需获取完整内容填充 TextArea。
通过 `Bridge.getTextContentById(textId)` 调用 `TextProvider.fetch_text_by_id()` 异步获取。

## 5. Bridge 状态与信号

### 5.1 新增状态

```python
_slice_mode: bool = False           # 是否处于载文模式
_slices: list[str] = []             # 分片文本列表
_current_slice: int = 0             # 当前片索引（从0开始）
_retype_enabled: bool = False       # 是否开启重打条件
_retype_metric: str = ""            # "speed" / "accuracy" / "wrong_char_count"
_retype_operator: str = ""          # "lt" / "le" / "ge" / "gt"
_retype_threshold: float = 0.0      # 重打阈值
_retype_shuffle: bool = False       # 重打时是否乱序
_slice_stats: list[dict] = []       # 每片的 SessionStat 快照（用于聚合计算）
_parent_source_key: str = ""        # 原文来源 key（用于日志/显示）
```

### 5.2 新增信号

| 信号 | 类型 | 说明 |
|---|---|---|
| `sliceModeChanged(bool)` | Signal | 进入/退出载文模式 |
| `sliceStatusChanged(str)` | Signal | 片进度更新（如 "3/5 | 上一片: 85CPM 98%"） |
| `allSlicesCompleted(str)` | Signal(str) | 全部片打完，携带聚合成绩消息 |

### 5.3 新增 Slot

| Slot | 参数 | 说明 |
|---|---|---|
| `setupSliceMode` | text, slice_size, retype_enabled, metric, operator, threshold, shuffle | 初始化载文状态，分片并加载第一片 |
| `collectSliceResult` | 无 | 收集当前片的 SessionStat，存入 _slice_stats |
| `isLastSlice` | 无 → bool | 当前片是否为最后一片 |
| `loadNextSlice` | 无 | 载入下一片 |
| `shouldRetype` | score_dict → bool | 检查成绩是否触发重打条件 |
| `reloadCurrentSlice` | 无 | 重打当前片 |
| `shuffleCurrentSlice` | 无 | 乱序当前片并载入 |
| `buildAggregateScore` | 无 → str | 计算聚合成绩，返回格式化消息 |
| `exitSliceMode` | 无 | 清理载文状态 |
| `getSliceStatus` | 无 → str | 返回当前片进度摘要 |
| `getTextListForSlice` | source_key → list | 返回某来源的文本列表（本地/远程） |
| `getTextContentById` | text_id | 异步获取远程文本内容，通过 textLoaded 信号返回 |

### 5.4 属性

```python
sliceMode = Property(bool, notify=sliceModeChanged)
```

## 6. 自动推进逻辑

### 6.1 typingEnded 拦截（QML 侧）

```qml
function onTypingEnded() {
    if (appBridge.sliceMode) {
        // 载文模式：跳过 EndDialog，自动推进
        appBridge.collectSliceResult()
        if (appBridge.isLastSlice()) {
            // 最后一片：弹出综合成绩
            var msg = appBridge.buildAggregateScore()
            endDialog.scoreMessage = msg
            endDialog.open()
            appBridge.exitSliceMode()
        } else {
            // 判断重打条件
            var lastStats = appBridge.getLastSliceStats()
            if (appBridge.shouldRetype(lastStats)) {
                if (appBridge.retypeShuffle) {
                    appBridge.shuffleCurrentSlice()
                } else {
                    appBridge.reloadCurrentSlice()
                }
            } else {
                appBridge.loadNextSlice()
            }
        }
    } else {
        // 正常模式：原有逻辑
        endDialog.scoreMessage = appBridge.getScoreMessage()
        endDialog.open()
    }
}
```

### 6.2 collectSliceResult 内部逻辑

```python
def collectSliceResult(self) -> None:
    """从 TypingService 取出当前片的 SessionStat 快照，存入 _slice_stats。"""
    stat = self._typing_adapter._typing_service.score_data
    self._slice_stats.append({
        "speed": stat.speed,
        "keyStroke": stat.keyStroke,
        "codeLength": stat.codeLength,
        "accuracy": stat.accuracy,
        "effectiveSpeed": stat.effectiveSpeed,
        "wrong_char_count": stat.wrong_char_count,
        "backspace_count": stat.backspace_count,
        "correction_count": stat.correction_count,
        "char_count": stat.char_count,
        "time": stat.time,
    })
    # 更新状态栏
    idx = self._current_slice + 1
    total = len(self._slice_stats)
    status = f"{idx}/{total} | 上一片: {stat.speed:.0f}CPM {stat.accuracy:.1f}%"
    self.sliceStatusChanged.emit(status)
```

### 6.3 buildAggregateScore 内部逻辑

```python
def buildAggregateScore(self) -> str:
    """计算所有片的聚合成绩，返回格式化消息。"""
    stats = self._slice_stats
    n = len(stats)
    if n == 0:
        return ""

    # 平均值指标
    avg_speed = sum(s["speed"] for s in stats) / n
    avg_keystroke = sum(s["keyStroke"] for s in stats) / n
    avg_code_length = sum(s["codeLength"] for s in stats) / n

    # 累加指标
    total_chars = sum(s["char_count"] for s in stats)
    total_wrong = sum(s["wrong_char_count"] for s in stats)
    total_backspace = sum(s["backspace_count"] for s in stats)
    total_correction = sum(s["correction_count"] for s in stats)
    total_time = sum(s["time"] for s in stats)

    # 派生指标
    accuracy = (total_chars - total_wrong) / total_chars * 100 if total_chars > 0 else 0
    effective_speed = avg_speed * accuracy / 100

    # 格式化（复用 ScoreGateway 的格式化逻辑）
    return self._score_gateway.format_aggregate_message(
        avg_speed=avg_speed,
        avg_keystroke=avg_keystroke,
        avg_code_length=avg_code_length,
        accuracy=accuracy,
        effective_speed=effective_speed,
        total_chars=total_chars,
        total_wrong=total_wrong,
        total_backspace=total_backspace,
        total_correction=total_correction,
        total_time=total_time,
        slice_count=n,
    )
```

## 7. 每片成绩原子化记录

### 7.1 机制

每片打完时，现有 `_check_typing_complete()` 正常执行：
1. `_typing_service.get_history_record()` → 返回 dict
2. `historyRecordUpdated.emit(record)` → QML HistoryArea 插入一行
3. `typingEnded.emit()` → QML 侧触发自动推进
4. 剪贴板自动复制成绩（已有逻辑）

**slice_index 注入方式：** TypingAdapter 新增 `_slice_index: int | None` 属性，Bridge 在加载每片时通过 `set_slice_index(idx)` 设置。`_check_typing_complete()` emit 前检查该属性，有则注入 record dict。

```python
# typing_adapter.py
_slice_index: int | None = None

def set_slice_index(self, idx: int | None) -> None:
    self._slice_index = idx

def _check_typing_complete(self) -> bool:
    # ... 原有判断 ...
    record = self._typing_service.get_history_record()
    if self._slice_index is not None:
        record["slice_index"] = self._slice_index
    self.historyRecordUpdated.emit(record)
    self.typingEnded.emit()
    # ...
```

Bridge 在 `loadSliceText()` 中设置：
```python
def loadSliceText(self, text: str) -> None:
    self._typing_adapter.set_slice_index(self._current_slice + 1)
    self._typing_adapter.prepare_for_text_load()
    self.textLoaded.emit(text, -1, f"载文 {self._current_slice + 1}/{len(self._slice_stats)}")
```

这样 record 只 emit 一次，天然携带 slice_index，无需重复 emit。

### 7.2 HistoryArea 显示片索引

**不新增列。** 在 `charNum` 列中追加标记：
- 普通模式：`"30"`（不变）
- 分片模式：`"30 [3/5]"`

QML 侧 `onHistoryRecordUpdated` 中，如果 record 含 `slice_index`，在插入前修改 `charNum` display value：

```qml
function onHistoryRecordUpdated(newRecord) {
    if (newRecord.slice_index !== undefined && newRecord.slice_index > 0) {
        var idx = newRecord.slice_index
        var total = appBridge.totalSliceCount
        newRecord.charNum = newRecord.charNum + " [" + idx + "/" + total + "]"
    }
    historyArea.tableModel.insertRow(0, newRecord)
}
```

### 7.3 剪贴板自动复制

每片打完时，`_check_typing_complete()` 调用 `_copy_score_message()` 复制到剪贴板。
载文模式下，ScoreGateway 的消息标题可改为"第 N 片成绩"：

```python
# score_gateway.py
def copy_score_message(self, score_data, text_title, slice_index=None):
    if slice_index is not None:
        title = f"第 {slice_index} 片成绩"
    else:
        title = text_title or "自定义文本"
    # ... 格式化并复制 ...
```

## 8. 成绩提交约束

**分片模式下不提交任何成绩到服务端。** 理由：服务端只记录一次性打完未分片全文的成绩，保证排行榜公平性。

**实现方式（零侵入）：** `loadSliceText()` 加载分片时，`textLoaded` 的 text_id 传 `-1`（纯本地文本标识）。已有 `_submit_score_async()` 中 `text_id <= 0` 判断为 false，自动跳过提交。无需新增任何守卫逻辑。

综合成绩（EndDialog 弹出的聚合数据）同样不提交，仅本地展示 + 剪贴板复制。

**正常模式不受影响：** 用户通过 ToolLine 的"载文"按钮走标准 Worker 链路载文时，行为与现在完全一致——本地源异步回查 text_id、网络源直接获取 text_id、成绩正常提交。

## 9. 完整数据流

```
用户点击"载文" → 打开 SliceConfigDialog
    │
    ├─ 来源选择 → Bridge.getTextListForSlice(source_key)
    │    ├─ 本地源 → 扫描目录/读取文件 → 同步返回列表
    │    └─ 远程源 → TextListWorker → 异步返回列表
    │
    ├─ 点击列表项 → TextArea 显示内容（可编辑）
    │    └─ 远程源 → Bridge.getTextContentById(id) → textLoaded → TextArea
    │
    └─ 点击"开始载文" → Bridge.setupSliceMode(text, size, retype_config)
         │
         ├─ 分片 text → _slices[]
         ├─ _current_slice = 0
         └─ loadSliceText(_slices[0])
              → textLoaded(plainText, -1, "载文 1/N")
              → TypingPage: applyLoadedText → 用户打字
                   │
                   typingEnded
                   │
                   ├─ collectSliceResult()       // 收集 SessionStat，注入 slice_index
                   │    → historyRecordUpdated(record_with_slice_index)
                   │    → HistoryArea 插入 "85CPM 98% 30 [1/5]"
                   │    → 剪贴板复制"第 1 片成绩"
                   │
                   ├─ isLastSlice()?
                   │    ├─ YES → buildAggregateScore()
                   │    │         → allSlicesCompleted(aggregate_msg)
                   │    │         → EndDialog 弹出综合成绩
                   │    │         → exitSliceMode()
                   │    │
                   │    └─ NO → shouldRetype(last_stats)?
                   │              ├─ YES + shuffle → shuffleCurrentSlice()
                   │              ├─ YES + 普通   → reloadCurrentSlice()
                   │              └─ NO           → loadNextSlice()
                   │                                   → textLoaded(plainText, -1, "载文 2/N")
                   │                                   → 继续打字...
                   │
                   └─ sliceStatusChanged → 底部状态栏更新
```

## 10. 需修改的文件清单

| 文件 | 改动 |
|---|---|
| `src/backend/presentation/bridge.py` | 新增载文状态、信号、Slot（核心改动） |
| `src/backend/presentation/adapters/typing_adapter.py` | `_slice_index` 属性 + `_check_typing_complete()` 注入 slice_index |
| `src/backend/application/gateways/score_gateway.py` | `format_aggregate_message()` + `copy_score_message()` 支持 slice_index |
| `src/qml/typing/ToolLine.qml` | "载文"按钮改为打开 Dialog |
| `src/qml/pages/TypingPage.qml` | `onTypingEnded` 增加 slice mode 分支 + 底部状态栏 |
| `src/qml/dialogs/SliceConfigDialog.qml` | **新建** 载文设置对话框 |
| `src/qml/typing/HistoryArea.qml` | 可选：charNum 列显示片索引标记 |
