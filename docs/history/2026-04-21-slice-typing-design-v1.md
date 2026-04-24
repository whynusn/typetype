# 载文（分片跟打）功能设计 v1（初版草案）

> 本文档为初版设计草案，后续将根据反馈微调后生成正式设计文档。

## 1. 背景与目标

连贯文本通常数百字，不利于用户短时间内对某几个字进行大量练习。"载文"功能允许用户将选定文本按指定字数分片，逐片跟打，并根据预设条件自动推进。

## 2. 架构方案

### 推荐方案 A：Bridge 集中管理状态 + QML 轻量层

Bridge 持有所有载文状态（分片列表、当前片索引、重打条件），typingEnded 时 Bridge 判断自动行为，QML 侧只做信号转发和 UI 显示。

**理由：** 当前 Bridge 已是信号枢纽，加一组载文状态是自然扩展。重打条件判断需要读 SessionStat，在 Bridge 侧最方便。

### 备选方案 B：QML 侧管理载文状态

QML 中用 JS 数组管理分片、判断重打条件。
**缺点：** QML/JS 不适合复杂状态管理，无法单元测试。

### 备选方案 C：新建 SliceAdapter 独立适配器
**缺点：** 架构改动大，过度工程。

## 3. UI 设计

### 3.1 ToolLine 改动

"载文"按钮点击后打开载文 Dialog（替换直接随机载文逻辑）。

### 3.2 载文 Dialog（SliceConfigDialog.qml）

```
┌─────────────────────────────────────────────┐
│  载文设置                           [×]      │
├─────────────────────────────────────────────┤
│  ┌─ 自定义输入 ──────────────────────────┐   │
│  │  [TextArea] 粘贴或输入自定义文本       │   │
│  └───────────────────────────────────────┘   │
│  ┌─ 从文本库选择 ────────────────────────┐   │
│  │  来源: [ComboBox]                      │   │
│  │  [ListView 文本1 / 文本2 / ...]       │   │
│  └───────────────────────────────────────┘   │
│  ┌─ 分片设置 ────────────────────────────┐   │
│  │  每片字数: [ComboBox: 20/30/50/100]   │   │
│  │  ☐ 全文载入（不分片）                  │   │
│  └───────────────────────────────────────┘   │
│  ┌─ 重打条件 ────────────────────────────┐   │
│  │  ☑ 开启重打条件                       │   │
│  │  当 [指标] [比较符] [阈值] 时重打      │   │
│  │  ☐ 重打时乱序                         │   │
│  └───────────────────────────────────────┘   │
│            [ 取消 ]    [ 开始载文 ]          │
└─────────────────────────────────────────────┘
```

## 4. Bridge 状态与信号

### 4.1 新增状态

```python
_slice_mode: bool = False
_slices: list[str] = []
_current_slice: int = 0
_retype_enabled: bool = False
_retype_metric: str = ""       # "speed" / "accuracy" / "wrong_char_count"
_retype_operator: str = ""     # "lt" / "le" / "ge" / "gt"
_retype_threshold: float = 0.0
_retype_shuffle: bool = False
```

### 4.2 新增信号

```python
sliceModeChanged = Signal(bool)
sliceStatusChanged = Signal(str)
```

### 4.3 新增 Slot

- `setupSliceMode(text, slice_size, retype_enabled, metric, operator, threshold, shuffle)`
- `getSliceStatus() -> str`
- `handleSliceTypingEnded()`

## 5. 自动推进逻辑

```
typingEnded → QML onTypingEnded:
  if sliceMode:
    score = getCurrentScore()
    if shouldRetype(score):
      reload or shuffle current slice
    elif hasMoreSlices():
      loadNextSlice()
    else:
      exitSliceMode() → EndDialog
  else:
    EndDialog（原有逻辑）
```

## 6. 数据流

```
[Dialog] setupSliceMode → Bridge 持有状态
Bridge.loadSliceText(slice[i]) → textLoaded → TypingPage 显示
用户打字 → typingEnded → Bridge.handleSliceTypingEnded
  → 判断重打 → reload/shuffle
  → 判断下一片 → loadNextSlice
  → 全部完成 → exitSliceMode + EndDialog
sliceStatusChanged → 底部状态栏更新
```
