# 成绩展示格式统一与 sliceStatusBar 导航 — 设计文档

## 背景

当前项目存在多个成绩输出端点（ScoreArea 实时栏、EndDialog 弹窗、HistoryArea 历史表格、剪贴板复制、聚合成绩），输出格式不统一，指标集和排列顺序各不一致。同时 sliceStatusBar 缺少快速切换上下片段的交互按钮。

## 目标

1. 统一所有成绩输出端点的指标集和排列顺序，采用木易跟打器风格（去除换行符后的单行纯文本）。
2. ScoreArea 实时栏仅保留 6 个精简指标。
3. 在 sliceStatusBar 上新增两个可点击组件，用于切换上一片段和下一片段。

## 统一指标集与顺序

完整指标集（排除暂未统计项与无统计数据的项）：
1. 速度 (字/分)
2. 击键 (击/秒)
3. 码长 (击/字)
4. 字数
5. 错字
6. 用时 (秒)
7. 键准 (%)
8. 回改
9. 键数
10. 退格

暂未统计指标（暂不加）：暂停次数、键法、左、右、理论码长、打词、打词率、选重

目前无回车统计，回车指标从统一指标集中移除。

## 各端点格式要求

| 端点 | 格式 | 指标数 |
|------|------|--------|
| ScoreArea | 精简 6 指标 | 速度、击键、码长、键准、字数、用时 |
| EndDialog | 多行 HTML（统一指标/顺序） | 完整 |
| HistoryArea | 表格行 | 完整（表头重排） |
| 剪贴板（普通模式） | 单行木易纯文本 | 完整 |
| 剪贴板（聚合成绩） | 单行木易纯文本 | 完整（聚合值） |

## 木易格式示例

单行纯文本（去除换行后）：
```
第6段 速度113.02 击键12.09 码长6.42 字数50 错字0 用时26.544秒 暂停0次0.000秒 键准93.51% 键法0% 左0 右1 理论码长1 打词0 打词率0% 选重0 回改2 键数321 退格2 回车1 第1次跟打
```

实际输出中，暂未统计和回车指标不展示。有效单行示例：
```
第6段 速度113.02 击键12.09 码长6.42 字数50 错字0 用时26.544秒 键准93.51% 回改2 键数321 退格2
```

弹窗 HTML 格式（换行分隔）：
```
速度: <b>113.02</b> 字/分<br>
击键: <b>12.09</b> 击/秒<br>
码长: <b>6.42</b> 击/字<br>
...
```

## 后端格式化职责

- `ScoreSummaryDTO`：
  - `to_html()` → 多行 HTML，供 EndDialog 使用
  - `to_plain_text()` → 多行纯文本（作为内部辅助）
  - `to_clipboard_text()` → 单行木易格式，供剪贴板使用
- `ScoreGateway`：
  - `build_score_message()` → 调用 `to_html()`
  - `copy_score_to_clipboard()` → 调用 `to_clipboard_text()`
  - `build_aggregate_message()` → 多行 HTML
  - `build_aggregate_plain_text()` → 单行木易格式

## sliceStatusBar 导航按钮

在 `sliceStatusBar` 的 RowLayout 末尾增加两个可点击组件：
- `← 上一段`：点击调用 `appBridge.loadPrevSlice()`
- `下一段 →`：点击调用 `appBridge.loadNextSlice()`

行为约束：
- 第1片：隐藏/禁用「上一段」按钮
- 最后一片：隐藏/禁用「下一段」按钮
- 切换后触发 `_load_current_slice()`，自动重置打字状态

## 新增后端接口

- `TypingSessionContext.back_slice()`：片索引减1，验证边界（不能小于1）
- `TypingAdapter.back_slice()` → `TypingSessionContext.back_slice()` → `_load_current_slice()`
- `Bridge.loadPrevSlice()` Slot：供 QML 调用

## 数据流

```
TypingService.score_data
    ↓
ScoreSummaryDTO.from_score_data()
    → to_html()           → ScoreGateway.build_score_message()       → EndDialog
    → to_clipboard_text() → ScoreGateway.copy_score_to_clipboard()   → 剪贴板
    → HistoryRecordDTO.from_score_data() → HistoryArea
    → 各属性代理 → ScoreArea
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `src/backend/models/dto/score_dto.py` | 重构 `ScoreSummaryDTO` 格式化方法；`HistoryRecordDTO` 字段排序；统一指标顺序 |
| `src/backend/application/gateways/score_gateway.py` | 更新 HTML/纯文本构建逻辑；聚合成绩单行格式化 |
| `src/backend/domain/services/typing_service.py` | `get_history_record()` 字段排序统一 |
| `src/backend/presentation/adapters/typing_adapter.py` | 新增 `back_slice()` 代理方法 |
| `src/backend/presentation/bridge.py` | 新增 `loadPrevSlice()` Slot；调整 `loadNextSlice()` 边界逻辑 |
| `src/backend/application/session_context.py` | 新增 `back_slice()` 方法 |
| `src/qml/typing/ScoreArea.qml` | 精简为6指标：速度、击键、码长、键准、字数、用时 |
| `src/qml/typing/HistoryArea.qml` | 表头/列宽重排为统一顺序 |
| `src/qml/pages/TypingPage.qml` | `sliceStatusBar` 新增上下段导航按钮 |
| `tests/test_score_dto.py` | 更新 DTO 测试 |
| `tests/test_session_stat.py` | 补充键准/其他属性测试 |
