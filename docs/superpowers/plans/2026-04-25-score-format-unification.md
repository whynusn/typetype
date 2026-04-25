# 成绩展示格式统一与 sliceStatusBar 导航 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一所有成绩输出端点的指标集和排列顺序（木易跟打器风格），精简 ScoreArea 为 6 指标，在 sliceStatusBar 上新增上下段导航按钮。

**Architecture:** 后端 `ScoreSummaryDTO` / `ScoreGateway` 集中管理格式化逻辑（HTML 多行 + 剪贴板单行），所有输出端点消费同一数据源；前端 QML 仅做展示层调整，无格式化逻辑。

**Tech Stack:** Python 3.12, PySide6, QML, pytest, ruff

---

## 文件变更总览

| 文件 | 变更 |
|------|------|
| `src/backend/models/dto/score_dto.py` | 重构 `ScoreSummaryDTO`：统一指标顺序，新增 `to_clipboard_text()`，移除 有效速度；`HistoryRecordDTO` 字段重排 |
| `src/backend/application/gateways/score_gateway.py` | 更新 HTML/纯文本构建逻辑；聚合成绩改用统一指标顺序 |
| `src/backend/domain/services/typing_service.py` | `get_history_record()` 字段顺序统一；`_last_slice_stats` 增加 `key_stroke_count` |
| `src/backend/presentation/adapters/typing_adapter.py` | 新增 `back_slice()` 代理方法 |
| `src/backend/presentation/bridge.py` | 新增 `sliceIndex` 属性和 `loadPrevSlice()` Slot；`loadNextSlice()` 补充信号发射 |
| `src/backend/application/session_context.py` | 新增 `back_slice()` 方法 |
| `src/qml/typing/ScoreArea.qml` | 精简为 6 指标：速度、击键、码长、键准、字数、用时 |
| `src/qml/typing/HistoryArea.qml` | 表头文本调整：`错字数`→`错字`，`时间`→`用时` |
| `src/qml/pages/TypingPage.qml` | `sliceStatusBar` 新增上下段导航按钮 |
| `tests/test_score_dto.py` | 更新 DTO 测试：指标数量、顺序、新格式化方法 |

---

### Task 1: 重构 ScoreSummaryDTO 与 HistoryRecordDTO

**Files:**
- Modify: `src/backend/models/dto/score_dto.py`
- Test: `tests/test_score_dto.py`

统一指标顺序（完整 10 项）：速度 → 击键 → 码长 → 错字 → 回改 → 退格 → 键准 → 字数 → 用时 → 键数

- [ ] **Step 1: 修改 ScoreSummaryDTO.from_score_data()**

将 `src/backend/models/dto/score_dto.py` 中 `ScoreSummaryDTO.from_score_data()` 替换为：

```python
    @classmethod
    def from_score_data(cls, score_data: "SessionStat") -> "ScoreSummaryDTO":
        """从领域对象构建成绩摘要 DTO。"""
        return cls(
            items=[
                ScoreSummaryItemDTO(
                    label="速度",
                    value=score_data.speed,
                    unit="字/分",
                    value_format=".2f",
                ),
                ScoreSummaryItemDTO(
                    label="击键",
                    value=score_data.keyStroke,
                    unit="击/秒",
                    value_format=".2f",
                ),
                ScoreSummaryItemDTO(
                    label="码长",
                    value=score_data.codeLength,
                    unit="击/字",
                    value_format=".2f",
                ),
                ScoreSummaryItemDTO(
                    label="错字",
                    value=score_data.wrong_char_count,
                    unit="字",
                    value_format="d",
                ),
                ScoreSummaryItemDTO(
                    label="回改",
                    value=score_data.correction_count,
                    unit="次",
                    value_format="d",
                ),
                ScoreSummaryItemDTO(
                    label="退格",
                    value=score_data.backspace_count,
                    unit="次",
                    value_format="d",
                ),
                ScoreSummaryItemDTO(
                    label="键准",
                    value=score_data.keyAccuracy,
                    unit="%",
                    value_format=".2f",
                ),
                ScoreSummaryItemDTO(
                    label="字数",
                    value=score_data.char_count,
                    unit="",
                    value_format="d",
                ),
                ScoreSummaryItemDTO(
                    label="用时",
                    value=score_data.time,
                    unit="秒",
                    value_format=".3f",
                ),
                ScoreSummaryItemDTO(
                    label="键数",
                    value=score_data.key_stroke_count,
                    unit="",
                    value_format="d",
                ),
            ]
        )
```

- [ ] **Step 2: 新增 to_clipboard_text() 方法**

在 `ScoreSummaryDTO` 中，在 `to_html()` 下方新增：

```python
    def to_clipboard_text(self) -> str:
        """渲染为木易跟打器风格单行纯文本。"""
        parts: list[str] = []
        for item in self.items:
            value_str = f"{item.value:{item.value_format}}"
            if item.unit in ("秒", "%"):
                parts.append(f"{item.label}{value_str}{item.unit}")
            else:
                parts.append(f"{item.label}{value_str}")
        return " ".join(parts)
```

- [ ] **Step 3: 修改 HistoryRecordDTO.to_dict() 字段顺序**

将 `HistoryRecordDTO.to_dict()` 替换为：

```python
    def to_dict(self) -> dict[str, float | int | str]:
        """输出与 QML 历史记录兼容的数据结构。"""
        return {
            "speed": self.speed,
            "keyStroke": self.key_stroke,
            "codeLength": self.code_length,
            "wrongNum": self.wrong_num,
            "correctionCount": self.correction_count,
            "backspaceCount": self.backspace_count,
            "keyAccuracy": self.key_accuracy,
            "charNum": self.char_num,
            "time": self.time,
            "date": self.date,
        }
```

- [ ] **Step 4: 更新 test_score_dto.py**

将 `tests/test_score_dto.py` 替换为：

```python
"""成绩 DTO 测试。"""

from src.backend.models.dto.score_dto import HistoryRecordDTO, ScoreSummaryDTO
from src.backend.models.entity.session_stat import SessionStat


class TestHistoryRecordDTO:
    """测试历史记录 DTO 转换"""

    def test_from_score_data_and_to_dict(self):
        """应可从领域对象转换为 QML 兼容字典"""
        score = SessionStat(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        dto = HistoryRecordDTO.from_score_data(score)
        result = dto.to_dict()

        assert result == {
            "speed": 240.0,
            "keyStroke": 5.0,
            "codeLength": 1.25,
            "wrongNum": 10,
            "correctionCount": 0,
            "backspaceCount": 0,
            "keyAccuracy": 100.0,
            "charNum": 240,
            "time": 60.0,
            "date": "2024-01-01 00:00:00",
        }


class TestScoreSummaryDTO:
    """测试成绩摘要 DTO"""

    def test_from_score_data(self):
        """应生成固定顺序的 10 项摘要"""
        score = SessionStat(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        dto = ScoreSummaryDTO.from_score_data(score)

        assert len(dto.items) == 10
        assert dto.items[0].label == "速度"
        assert dto.items[1].label == "击键"
        assert dto.items[2].label == "码长"
        assert dto.items[3].label == "错字"
        assert dto.items[4].label == "回改"
        assert dto.items[5].label == "退格"
        assert dto.items[6].label == "键准"
        assert dto.items[7].label == "字数"
        assert dto.items[8].label == "用时"
        assert dto.items[9].label == "键数"

    def test_to_plain_text(self):
        """应输出多行纯文本格式摘要"""
        score = SessionStat(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        text = ScoreSummaryDTO.from_score_data(score).to_plain_text()

        assert "速度:" in text
        assert "字/分" in text
        assert "\n" in text

    def test_to_html(self):
        """应输出 HTML 格式摘要"""
        score = SessionStat(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        text = ScoreSummaryDTO.from_score_data(score).to_html()

        assert "<b>" in text
        assert "</b>" in text
        assert "<br>" in text

    def test_to_clipboard_text(self):
        """应输出单行木易格式"""
        score = SessionStat(
            time=60.0,
            key_stroke_count=300,
            char_count=240,
            wrong_char_count=10,
            date="2024-01-01 00:00:00",
        )

        text = ScoreSummaryDTO.from_score_data(score).to_clipboard_text()

        assert "速度240.00" in text
        assert "击键5.00" in text
        assert "码长1.25" in text
        assert "字数240" in text
        assert "错字10" in text
        assert "用时60.000秒" in text
        assert "键准100.00%" in text
        assert "回改0" in text
        assert "键数300" in text
        assert "退格0" in text
        assert "\n" not in text
```

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/test_score_dto.py -v`
Expected: 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/backend/models/dto/score_dto.py tests/test_score_dto.py
git commit -m "refactor(dto): 统一 ScoreSummaryDTO 指标顺序，新增剪贴板单行格式"
```

---

### Task 2: 更新 ScoreGateway 格式化方法

**Files:**
- Modify: `src/backend/application/gateways/score_gateway.py`

- [ ] **Step 1: 修改 copy_score_to_clipboard**

将 `score_gateway.py` 中 `copy_score_to_clipboard()` 替换为：

```python
    def copy_score_to_clipboard(self, score_data: SessionStat | None) -> None:
        """复制分数摘要木易单行格式到剪贴板。"""
        if not score_data:
            return
        plain_text = ScoreSummaryDTO.from_score_data(score_data).to_clipboard_text()
        self._clipboard.setText(plain_text)
```

- [ ] **Step 2: 重构 build_aggregate_message**

将 `build_aggregate_message()` 替换为：

```python
    def build_aggregate_message(self, slice_stats: list[dict], slice_count: int) -> str:
        """构建分片模式综合成绩 HTML 消息。

        Args:
            slice_stats: 每片 SessionStat 快照列表（dict 格式）
            slice_count: 片数
        """
        n = len(slice_stats)
        if n == 0:
            return ""

        avg_speed = sum(s["speed"] for s in slice_stats) / n
        avg_keystroke = sum(s["keyStroke"] for s in slice_stats) / n
        avg_code_length = sum(s["codeLength"] for s in slice_stats) / n
        total_chars = sum(s["char_count"] for s in slice_stats)
        total_wrong = sum(s["wrong_char_count"] for s in slice_stats)
        total_backspace = sum(s["backspace_count"] for s in slice_stats)
        total_correction = sum(s["correction_count"] for s in slice_stats)
        total_time = sum(s["time"] for s in slice_stats)
        total_key_strokes = sum(s.get("key_stroke_count", 0) for s in slice_stats)
        key_accuracy = (
            (total_key_strokes - total_backspace - total_correction * avg_code_length)
            / total_key_strokes
            * 100
            if total_key_strokes > 0
            else 100.0
        )

        items = [
            ("速度", avg_speed, "字/分", ".2f"),
            ("击键", avg_keystroke, "击/秒", ".2f"),
            ("码长", avg_code_length, "击/字", ".2f"),
            ("错字", total_wrong, "字", "d"),
            ("回改", total_correction, "次", "d"),
            ("退格", total_backspace, "次", "d"),
            ("键准", key_accuracy, "%", ".2f"),
            ("字数", total_chars, "", "d"),
            ("用时", total_time, "秒", ".3f"),
            ("键数", total_key_strokes, "", "d"),
        ]

        lines = [f"<b>综合成绩（{slice_count}片）</b><br>"]
        for label, value, unit, fmt in items:
            if unit == "%":
                lines.append(f"{label}: <b>{value:{fmt}}</b>{unit}<br>")
            elif unit:
                lines.append(f"{label}: <b>{value:{fmt}}</b> {unit}<br>")
            else:
                lines.append(f"{label}: <b>{value:{fmt}}</b><br>")
        return "".join(lines)
```

- [ ] **Step 3: 重构 build_aggregate_plain_text**

将 `build_aggregate_plain_text()` 替换为：

```python
    def build_aggregate_plain_text(
        self, slice_stats: list[dict], slice_count: int
    ) -> str:
        """构建分片模式综合成绩木易单行纯文本（用于剪贴板）。"""
        n = len(slice_stats)
        if n == 0:
            return ""

        avg_speed = sum(s["speed"] for s in slice_stats) / n
        avg_keystroke = sum(s["keyStroke"] for s in slice_stats) / n
        avg_code_length = sum(s["codeLength"] for s in slice_stats) / n
        total_chars = sum(s["char_count"] for s in slice_stats)
        total_wrong = sum(s["wrong_char_count"] for s in slice_stats)
        total_backspace = sum(s["backspace_count"] for s in slice_stats)
        total_correction = sum(s["correction_count"] for s in slice_stats)
        total_time = sum(s["time"] for s in slice_stats)
        total_key_strokes = sum(s.get("key_stroke_count", 0) for s in slice_stats)
        key_accuracy = (
            (total_key_strokes - total_backspace - total_correction * avg_code_length)
            / total_key_strokes
            * 100
            if total_key_strokes > 0
            else 100.0
        )

        parts = [
            f"速度{avg_speed:.2f}",
            f"击键{avg_keystroke:.2f}",
            f"码长{avg_code_length:.2f}",
            f"字数{total_chars:d}",
            f"错字{total_wrong:d}",
            f"用时{total_time:.3f}秒",
            f"键准{key_accuracy:.2f}%",
            f"回改{total_correction:d}",
            f"键数{total_key_strokes:d}",
            f"退格{total_backspace:d}",
        ]
        return f"综合成绩（{slice_count}片） " + " ".join(parts)
```

- [ ] **Step 4: Commit**

```bash
git add src/backend/application/gateways/score_gateway.py
git commit -m "refactor(gateway): 聚合成绩改用统一指标顺序与木易单行格式"
```

---

### Task 3: TypingService 更新历史记录字段顺序与分片快照

**Files:**
- Modify: `src/backend/domain/services/typing_service.py`

- [ ] **Step 1: 修改 get_history_record() 字段顺序**

将 `get_history_record()` 替换为：

```python
    def get_history_record(self) -> dict[str, float | int | str]:
        """获取历史记录。"""
        self._state.score_data.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "speed": round(self._state.score_data.speed, 2),
            "keyStroke": round(self._state.score_data.keyStroke, 2),
            "codeLength": round(self._state.score_data.codeLength, 2),
            "wrongNum": self._state.score_data.wrong_char_count,
            "correctionCount": self._state.score_data.correction_count,
            "backspaceCount": self._state.score_data.backspace_count,
            "keyAccuracy": round(self._state.score_data.keyAccuracy, 2),
            "charNum": self._state.score_data.char_count,
            "time": round(self._state.score_data.time, 2),
            "date": self._state.score_data.date,
        }
```

- [ ] **Step 2: Commit**

```bash
git add src/backend/domain/services/typing_service.py
git commit -m "refactor(typing_service): 统一历史记录字段顺序"
```

---

### Task 4: 分片快照增加 key_stroke_count

**Files:**
- Modify: `src/backend/presentation/adapters/typing_adapter.py`

- [ ] **Step 1: 修改 _check_typing_complete 中的快照字段**

将 `_check_typing_complete()` 中捕获 `_last_slice_stats` 的代码段替换为：

```python
            # 分片模式：在任何清理之前捕获 score_data 快照
            if self._slice_index is not None:
                s = self._typing_service.score_data
                self._last_slice_stats = {
                    "speed": s.speed,
                    "keyStroke": s.keyStroke,
                    "codeLength": s.codeLength,
                    "accuracy": s.accuracy,
                    "keyAccuracy": s.keyAccuracy,
                    "effectiveSpeed": s.effectiveSpeed,
                    "wrong_char_count": s.wrong_char_count,
                    "backspace_count": s.backspace_count,
                    "correction_count": s.correction_count,
                    "char_count": s.char_count,
                    "key_stroke_count": s.key_stroke_count,
                    "time": s.time,
                }
```

- [ ] **Step 2: Commit**

```bash
git add src/backend/presentation/adapters/typing_adapter.py
git commit -m "fix(adapter): 分片快照补充 key_stroke_count 供聚合成绩使用"
```

---

### Task 5: 新增 back_slice 后端接口

**Files:**
- Modify: `src/backend/application/session_context.py`
- Modify: `src/backend/presentation/adapters/typing_adapter.py`
- Modify: `src/backend/presentation/bridge.py`

- [ ] **Step 1: 在 SessionContext 中新增 back_slice()**

在 `src/backend/application/session_context.py` 的 `advance_slice()` 下方新增：

```python
    def back_slice(self) -> None:
        if (
            self._source_mode == SourceMode.SLICE
            and self._slice_index > 1
        ):
            self._slice_index -= 1
            self._phase = SessionPhase.READY
```

- [ ] **Step 2: 在 TypingAdapter 中新增 back_slice() 代理**

在 `src/backend/presentation/adapters/typing_adapter.py` 的 `advance_slice()` 下方新增：

```python
    def back_slice(self) -> None:
        """代理：回退到上一片。"""
        if self._session_context:
            self._session_context.back_slice()
```

- [ ] **Step 3: 在 Bridge 中新增 sliceIndex 属性和 loadPrevSlice Slot**

在 `src/backend/presentation/bridge.py` 的 `totalSliceCount` property 下方新增 `sliceIndex` property：

```python
    @Property(int, notify=sliceModeChanged)
    def sliceIndex(self) -> int:
        return self._typing_adapter.slice_index
```

在 `loadNextSlice` Slot 下方新增：

```python
    @Slot()
    def loadPrevSlice(self) -> None:
        """载入上一片。"""
        if self._typing_adapter.slice_index > 1:
            self._typing_adapter.back_slice()
            self.sliceModeChanged.emit()
            self._load_current_slice()
```

同时修改现有的 `loadNextSlice`，在 `advance_slice()` 后补充信号发射：

将：
```python
    @Slot()
    def loadNextSlice(self) -> None:
        """载入下一片。"""
        if not self._typing_adapter.is_last_slice():
            self._typing_adapter.advance_slice()
            self._load_current_slice()
```

替换为：

```python
    @Slot()
    def loadNextSlice(self) -> None:
        """载入下一片。"""
        if not self._typing_adapter.is_last_slice():
            self._typing_adapter.advance_slice()
            self.sliceModeChanged.emit()
            self._load_current_slice()
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/application/session_context.py src/backend/presentation/adapters/typing_adapter.py src/backend/presentation/bridge.py
git commit -m "feat(slice): 新增 back_slice 接口与 sliceIndex QML 属性"
```

---

### Task 6: 精简 ScoreArea 为 6 指标

**Files:**
- Modify: `src/qml/typing/ScoreArea.qml`

- [ ] **Step 1: 重写 RowLayout 中的 PillButton**

将 `src/qml/typing/ScoreArea.qml` 中整个 `RowLayout` 替换为：

```qml
    RowLayout {
        id: rowLayout
        anchors.fill: parent
        anchors.leftMargin: 20

        PillButton {
            id: typeSpeed
            text: "速度: " + (appBridge ? appBridge.typeSpeed.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyStroke
            text: "击键: " + (appBridge ? appBridge.keyStroke.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: codeLength
            text: "码长: " + (appBridge ? appBridge.codeLength.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyAccuracy
            text: "键准: " + (appBridge ? appBridge.keyAccuracy.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: charNum
            text: "字数: " + (appBridge ? appBridge.charNum : 0)
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: totalTime
            text: "用时: " + (appBridge ? appBridge.totalTime.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add src/qml/typing/ScoreArea.qml
git commit -m "refactor(qml): ScoreArea 精简为速度/击键/码长/键准/字数/用时6指标"
```

---

### Task 7: HistoryArea 表头文本调整

**Files:**
- Modify: `src/qml/typing/HistoryArea.qml`

- [ ] **Step 1: 修改表头模型**

将 `src/qml/typing/HistoryArea.qml` 中的：
```qml
        model: ["速度", "击键", "码长", "错字数", "回改", "退格", "键准", "字数", "时间", "日期"]
```
替换为：
```qml
        model: ["速度", "击键", "码长", "错字", "回改", "退格", "键准", "字数", "用时", "日期"]
```

- [ ] **Step 2: Commit**

```bash
git add src/qml/typing/HistoryArea.qml
git commit -m "refactor(qml): HistoryArea 表头文本统一为错字/用时"
```

---

### Task 8: sliceStatusBar 新增导航按钮

**Files:**
- Modify: `src/qml/pages/TypingPage.qml`

- [ ] **Step 1: 修改 sliceStatusBar 的 RowLayout**

将 `src/qml/pages/TypingPage.qml` 中 `sliceStatusBar` 内的 `RowLayout` 替换为：

```qml
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 10

                            Rectangle {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                radius: 11
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.primaryColor + "20"
                                    : "#4b88ff20"

                                Text {
                                    anchors.centerIn: parent
                                    text: "片"
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.primaryColor
                                        : "#4b88ff"
                                }
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    text: typingPage.sliceStatusPrimaryText()
                                    font.pixelSize: 13
                                    font.bold: true
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.textColor
                                        : "#222"
                                }

                                Text {
                                    text: typingPage.sliceStatusSecondaryText().length > 0
                                        ? typingPage.sliceStatusSecondaryText()
                                        : "分片模式下的成绩仅本地记录，不提交排行榜"
                                    font.pixelSize: 11
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.textSecondaryColor
                                        : "#666"
                                }
                            }

                            Item { Layout.fillWidth: true }

                            Button {
                                text: "\u2190 上一段"
                                enabled: appBridge && appBridge.sliceIndex > 1
                                visible: enabled
                                onClicked: {
                                    if (appBridge) {
                                        appBridge.loadPrevSlice();
                                    }
                                }
                            }

                            Button {
                                text: "下一段 \u2192"
                                enabled: appBridge && !appBridge.isLastSlice()
                                visible: enabled
                                onClicked: {
                                    if (appBridge) {
                                        appBridge.loadNextSlice();
                                    }
                                }
                            }
                        }
```

- [ ] **Step 2: Commit**

```bash
git add src/qml/pages/TypingPage.qml
git commit -m "feat(qml): sliceStatusBar 新增上一段/下一段导航按钮"
```

---

### Task 9: 全量回归测试

**Files:**
- All modified files

- [ ] **Step 1: 运行 pytest**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: 运行 ruff check**

Run: `uv run ruff check .`
Expected: No errors

- [ ] **Step 3: 运行 ruff format check**

Run: `uv run ruff format --check .`
Expected: No changes needed

- [ ] **Step 4: 手动验证清单**

启动应用后验证：
- [ ] ScoreArea 只显示 6 个指标（速度/击键/码长/键准/字数/用时）
- [ ] 正常模式打字完成后，EndDialog 显示完整 10 项指标且顺序正确
- [ ] 点击 EndDialog 确认后，剪贴板内容为单行木易格式（无换行）
- [ ] HistoryArea 表头为：速度/击键/码长/错字/回改/退格/键准/字数/用时/日期
- [ ] 载文模式下 sliceStatusBar 显示上一段/下一段按钮
- [ ] 第 1 片时「上一段」按钮隐藏
- [ ] 最后一片时「下一段」按钮隐藏
- [ ] 点击上下段按钮后，打字状态重置，片计数器更新
- [ ] 载文模式最后一片结束后，聚合成绩弹窗格式正确
- [ ] 聚合成绩剪贴板复制为单行格式

- [ ] **Step 5: Commit（如有格式修复）**

```bash
git add -A
git commit -m "style: ruff format 修复" || echo "No changes to commit"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ 统一指标集和排列顺序 — Task 1, Task 2
- ✅ ScoreArea 精简 6 指标 — Task 6
- ✅ EndDialog HTML 多行格式 — Task 1, Task 2
- ✅ 剪贴板单行木易格式 — Task 1, Task 2
- ✅ HistoryArea 表头统一 — Task 7
- ✅ 聚合成绩统一格式 — Task 2
- ✅ sliceStatusBar 导航按钮 — Task 5, Task 8
- ✅ 片计数器同步更新 — Task 5 (sliceModeChanged 信号)

**2. Placeholder scan:** 无 TBD/TODO/占位符。

**3. Type consistency:**
- `back_slice()` 在 SessionContext / TypingAdapter / Bridge 中签名一致
- `sliceIndex` property 类型为 `int`，与 `totalSliceCount` 一致
- `loadPrevSlice()` / `loadNextSlice()` 均为无参 Slot，行为对称
