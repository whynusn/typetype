# 分片载文模式：QTextCursor 越界 + 达标次数累计 Bug 修复

**日期**: 2026-04-27
**状态**: 已修复

---

## 问题现象

1. **QTextCursor 越界警告**：分片载文模式下，每打完一个片段都会触发 `QTextCursor::setPosition: Position '9' out of range` 警告日志。不影响功能但污染日志输出。
2. **达标次数跨轮累计**：分片载文模式下打完一轮全文后，第二轮打到同一片段时，达标次数显示为上一轮累计值。导致仅一次达标就触发自动载入下一段，与预期不符。正确行为应为：同一片段内连续重打达标次数累加，离开片段后再回来时达标次数归零。

## 根因分析

### 根因 1：清空 UpperPane 时光标仍在旧位置

`TypingPage.qml` 的 `onTypingEnded` 处理函数中，直接设置 `upperPane.text = ""` 清空显示区。此时 UpperPane 内部的 QTextCursor 仍停留在旧位置（片段末尾），Qt 在清空文档后尝试将光标定位到旧位置，但文档已为空（characterCount=1），导致越界。

**关键时序**：
```
_check_typing_complete()
  → is_read_only = True
  → self._cursor = None          ← Python 侧防护到位
  → typingEnded.emit()
    → QML onTypingEnded:
      → lowerPane.text = ""      ← 触发 onCursorPositionChanged → setCursorPos(0)
      → upperPane.text = ""      ← Qt 内部光标仍在位置9，文档清空后越界
```

Python 侧的 `self._cursor = None` 防护只覆盖了 Python 的 `_color_text` 调用路径，无法阻止 Qt C++ 层的内部光标管理。

### 根因 2：达标次数仅在循环回绕时归零

`TypingSessionContext._slice_pass_counts` 按片段索引存储累计值。原代码的归零逻辑：

```python
# loadNextSlice 中（修复前）
if next_idx <= current:
    self._typing_adapter.reset_slice_pass_count(next_idx)
```

仅在无尽循环回绕时（`next_idx=1 < current=N`）重置。其他场景：
- `loadPrevSlice`：不重置
- `loadRandomSlice`：不重置
- trainer/local_article 后端：`setup_sourced_slice_mode(reset_counts=False)` 保留累计值

正确语义是：达标次数的生命周期是"一次片段访问"，而非"片段索引的终身累计"。

## 修复方案

### 修复 1：清空文本前重置光标

**文件**: `src/qml/pages/TypingPage.qml`

```qml
// 修复前
upperPane.text = "";

// 修复后
upperPane.setCursorAndScroll(0, false);
upperPane.text = "";
```

**补充防护**（`src/backend/presentation/adapters/typing_adapter.py`）：

`_color_text` 的边界检查从仅校验 `begin_pos > doc_len` 加强为同时校验 `begin_pos + n > doc_len`，防止 `movePosition` 越界：

```python
# 修复前
if begin_pos > doc_len:
    return

# 修复后
if begin_pos + n > doc_len or begin_pos >= doc_len:
    return
```

### 修复 2：片段切换时重置达标次数

**文件**: `src/backend/presentation/bridge.py`

| 场景 | 修复前 | 修复后 |
|:--- |:--- |:---|
| `loadNextSlice`（纯文本后端） | 仅循环回绕时重置 | 始终重置目标片段 |
| `_load_random_slice`（纯文本后端） | 仅循环回绕时重置 | 始终重置目标片段 |
| `loadPrevSlice`（纯文本后端） | 不重置 | 重置目标片段 |
| `handleSliceRetype`（所有后端） | 不重置 | 不重置（正确：同一片段重打应累加） |
| trainer 后端片段切换 | 不重置 | `index != prev_index` 时重置 |
| local_article 后端片段切换 | 不重置 | `index != prev_index` 时重置 |

核心改动示例：

```python
# loadNextSlice（纯文本后端）
self._typing_adapter.reset_slice_pass_count(next_idx)  # 新增
self._typing_adapter.set_slice_index(next_idx)

# trainer 后端
if not is_initial and index != prev_index:              # 新增
    self._typing_adapter.reset_slice_pass_count(index)  # 新增
```

## 修改文件清单

| 文件 | 修改 |
|:--- |:---|
| `src/qml/pages/TypingPage.qml` | `onTypingEnded` 中清空 `upperPane.text` 前先调用 `setCursorAndScroll(0)` |
| `src/backend/presentation/adapters/typing_adapter.py` | `_color_text` 边界检查加强：`begin_pos + n > doc_len` |
| `src/backend/presentation/bridge.py` | `loadNextSlice`/`_load_random_slice`/`loadPrevSlice` 片段切换时重置达标次数；trainer/local_article 后端 `index != prev_index` 时重置 |
| `tests/test_session_context.py` | 新增 `test_pass_count_resets_on_revisit` 测试 |

## 验证结果

- 403 测试全部通过（含 1 个新增测试）
- ruff lint 全部通过
- ruff format 全部通过
