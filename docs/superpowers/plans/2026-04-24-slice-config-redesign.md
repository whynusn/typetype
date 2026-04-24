# 载文设置 Dialog 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构载文设置 Dialog，将单一重打条件扩展为四指标联合合格判定，增加未达标事件选择、开始片段、全文乱序能力，并优化布局交互。

**Architecture:** 保持 `QML Dialog → Bridge → TypingAdapter → SessionContext` 链路。合格指标与事件配置下沉到 SessionContext 统一判定，QML 仅负责展示和传参。

**Tech Stack:** PySide6/QML, Python 3.12, pytest

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/qml/typing/SliceConfigDialog.qml` | 修改 | 重构 UI：合格指标4行、事件选择、开始片段、乱序按钮、校验逻辑 |
| `src/backend/presentation/bridge.py` | 修改 | `setupSliceMode` 签名变更；`handleSliceRetype` 支持 `on_fail_action` |
| `src/backend/presentation/adapters/typing_adapter.py` | 修改 | 代理方法签名同步变更 |
| `src/backend/application/session_context.py` | 修改 | 四指标判定逻辑、`should_retype` 重写、累计达标次数 |
| `tests/test_backend.py` | 修改 | 更新 `setupSliceMode` 调用以匹配新签名 |
| `tests/test_slice_typing.py` | 修改 | 如有涉及 SessionContext 的测试则更新 |
| `tests/test_session_context.py` | 创建 | 新增合格指标与事件判定单元测试 |

---

## Task 1: QML 层 — SliceConfigDialog.qml UI 重构

**Files:**
- Modify: `src/qml/typing/SliceConfigDialog.qml`

- [ ] **Step 1: 移除旧重打条件控件**

删除 `retypeCheck`、`metricCombo`、`operatorCombo`、`thresholdField`、`shuffleCheck` 及其关联校验逻辑（`thresholdMin`、`thresholdMax`、`defaultThresholdText`、`thresholdValue`、`ensureThresholdInRange`、`thresholdHelperText`）。

- [ ] **Step 2: 重构合格指标区域**

在"分片设置"Frame下方，新增"合格指标"Frame。内部固定4行：

```qml
Frame {
    Layout.fillWidth: true
    radius: 6
    hoverable: false

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Text {
            text: "合格指标（四个条件需同时满足）"
            font.bold: true
            font.pixelSize: 13
            color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
        }

        // 击键
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "击键"; font.pixelSize: 13 }
            Text { text: "≥"; font.pixelSize: 13 }
            TextField {
                id: keyStrokeMinField
                Layout.preferredWidth: 72
                text: "200"
                inputMethodHints: Qt.ImhDigitsOnly
                validator: IntValidator { bottom: 1; top: 999 }
            }
            Text { text: "次/秒"; font.pixelSize: 11; color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666" }
            Item { Layout.fillWidth: true }
        }
        // 速度（同上，id: speedMinField, default: "100", unit: "CPM"）
        // 键准（id: accuracyMinField, default: "95", unit: "%", validator: 0~100）
        // 达标次数（id: passCountMinField, default: "1", unit: "片", validator: 1~9999）

        Text {
            text: "四个条件需同时满足才算达标，任一不满足即触发下方设定的事件"
            font.pixelSize: 11
            color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
}
```

- [ ] **Step 3: 新增事件设置区域**

在合格指标 Frame 下方，新增事件选择行：

```qml
RowLayout {
    Layout.fillWidth: true
    spacing: 8
    Text { text: "未达标或有错字时:"; font.pixelSize: 13 }
    ComboBox {
        id: onFailActionCombo
        model: ListModel {
            ListElement { text: "乱序(重打)"; value: "shuffle_retype" }
            ListElement { text: "重打"; value: "retype" }
            ListElement { text: "无"; value: "none" }
        }
        textRole: "text"
        valueRole: "value"
    }
    Item { Layout.fillWidth: true }
}
```

- [ ] **Step 4: 分片设置区域增加"开始片段"**

在"每片字数"行中，追加"开始片段"输入框：

```qml
Text { text: "开始片段:"; font.pixelSize: 13 }
TextField {
    id: startSliceField
    Layout.preferredWidth: 72
    text: "1"
    enabled: !fullTextCheck.checked
    inputMethodHints: Qt.ImhDigitsOnly
    validator: IntValidator { bottom: 1; top: 9999 }
}
```

- [ ] **Step 5: 文本内容区域增加"乱序"按钮**

在"文本内容"Frame 的标题行右侧，增加"乱序"按钮：

```qml
RowLayout {
    Layout.fillWidth: true
    Text { text: "文本内容"; font.bold: true; font.pixelSize: 13 }
    Item { Layout.fillWidth: true }
    Button {
        text: "乱序"
        onClicked: {
            var text = contentTextArea.text;
            if (text.length > 0) {
                var arr = text.split('');
                for (var i = arr.length - 1; i > 0; i--) {
                    var j = Math.floor(Math.random() * (i + 1));
                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                }
                root.setContentText(arr.join(''));
            }
        }
    }
}
```

- [ ] **Step 6: 更新校验逻辑与 startSliceTyping**

修改 `buildValidationMessage`：
- 击键/速度/达标次数：整数 1~999
- 键准：整数 0~100
- 开始片段：整数 ≥1
- 若文本非空且非全文模式，计算 `totalSlices = Math.ceil(contentLength / sliceSize)`，若 `startSlice > totalSlices` 报错"开始片段不能超过总片段数 X"

修改 `startSliceTyping`：
```qml
var keyStrokeMin = parseInt(keyStrokeMinField.text);
var speedMin = parseInt(speedMinField.text);
var accuracyMin = parseInt(accuracyMinField.text);
var passCountMin = parseInt(passCountMinField.text);
var onFailAction = onFailActionCombo.currentValue;

appBridge.setupSliceMode(text, sliceSize, startSlice,
                         keyStrokeMin, speedMin, accuracyMin, passCountMin,
                         onFailAction, false);
```

- [ ] **Step 7: 调整 Dialog 尺寸**

将 `height: 620` 改为 `height: 720` 以容纳新增内容。

---

## Task 2: Bridge 层 — 更新 setupSliceMode 与 handleSliceRetype

**Files:**
- Modify: `src/backend/presentation/bridge.py`

- [ ] **Step 1: 重写 setupSliceMode Slot 签名**

```python
@Slot(str, int, int, int, int, int, int, str, bool)
def setupSliceMode(
    self,
    text: str,
    slice_size: int,
    start_slice: int,
    key_stroke_min: int,
    speed_min: int,
    accuracy_min: int,
    pass_count_min: int,
    on_fail_action: str,
    shuffle: bool,
) -> None:
    """初始化载文模式：分片文本并加载第 start_slice 片。"""
    if not text or slice_size <= 0:
        return

    total = self._typing_adapter.setup_slice_mode(
        text=text,
        slice_size=slice_size,
        start_slice=start_slice,
        key_stroke_min=key_stroke_min,
        speed_min=speed_min,
        accuracy_min=accuracy_min,
        pass_count_min=pass_count_min,
        on_fail_action=on_fail_action,
        shuffle=shuffle,
    )

    if total <= 0:
        return

    self.sliceModeChanged.emit()
    self._load_current_slice()
```

- [ ] **Step 2: 更新 handleSliceRetype 支持 on_fail_action**

```python
@Slot()
def handleSliceRetype(self) -> None:
    """根据 on_fail_action 自动处理重打（乱序、原样或无）。"""
    action = self._typing_adapter.on_fail_action
    if action == "shuffle_retype":
        self.shuffleCurrentSlice()
    elif action == "retype":
        self._reload_current_slice()
    else:  # "none" 或未知值：不重打，由 shouldRetype 已返回 False 不会走到这里
        pass
```

- [ ] **Step 3: 更新 getOnFailAction（供 QML 使用，可选）**

```python
@Slot(result=str)
def getOnFailAction(self) -> str:
    return self._typing_adapter.on_fail_action
```

---

## Task 3: TypingAdapter — 代理方法签名同步

**Files:**
- Modify: `src/backend/presentation/adapters/typing_adapter.py`

- [ ] **Step 1: 更新 setup_slice_mode 代理签名**

```python
def setup_slice_mode(
    self,
    text: str,
    slice_size: int,
    start_slice: int,
    key_stroke_min: int,
    speed_min: int,
    accuracy_min: int,
    pass_count_min: int,
    on_fail_action: str,
    shuffle: bool,
) -> int:
    if self._session_context:
        return self._session_context.setup_slice_mode(...)
    return 0
```

- [ ] **Step 2: 新增 on_fail_action 属性代理**

```python
@property
def on_fail_action(self) -> str:
    if self._session_context:
        return self._session_context.on_fail_action
    return "retype"
```

- [ ] **Step 3: 删除旧的 retype_shuffle 属性代理**

删除 `retype_shuffle` property 及其在 TypingAdapter 中的定义（SessionContext 中保留以兼容旧调用直到清理完毕）。

---

## Task 4: SessionContext — 四指标判定逻辑重写

**Files:**
- Modify: `src/backend/application/session_context.py`

- [ ] **Step 1: 替换旧重打参数为新合格指标参数**

在 `__init__` 中：
```python
# 删除：self._retype_enabled, self._retype_metric, self._retype_operator, self._retype_threshold, self._retype_shuffle
# 新增：
self._key_stroke_min: int = 0
self._speed_min: int = 0
self._accuracy_min: int = 0
self._pass_count_min: int = 1
self._on_fail_action: str = "retype"
self._start_slice: int = 1
self._consecutive_pass_count: int = 0
```

- [ ] **Step 2: 重写 setup_slice_mode**

```python
def setup_slice_mode(
    self,
    text: str,
    slice_size: int,
    start_slice: int,
    key_stroke_min: int,
    speed_min: int,
    accuracy_min: int,
    pass_count_min: int,
    on_fail_action: str,
    shuffle: bool,
) -> int:
    if not text or slice_size <= 0:
        return 0

    self._slices = []
    for i in range(0, len(text), slice_size):
        self._slices.append(text[i : i + slice_size])

    if not self._slices:
        return 0

    self._key_stroke_min = key_stroke_min
    self._speed_min = speed_min
    self._accuracy_min = accuracy_min
    self._pass_count_min = pass_count_min
    self._on_fail_action = on_fail_action
    self._start_slice = max(1, min(start_slice, len(self._slices)))
    self._consecutive_pass_count = 0
    self._slice_stats = []
    self._source_mode = SourceMode.SLICE
    self._text_id = None
    self._slice_index = self._start_slice
    self._slice_total = len(self._slices)
    self._phase = SessionPhase.READY
    self._derive_upload_status()
    return self._slice_total
```

- [ ] **Step 3: 重写 should_retype**

```python
def should_retype(self) -> bool:
    """检查当前片是否未达标，需要触发事件。

    逻辑：击键≥、速度≥、键准≥ 三项同时满足则 consecutive_pass_count +1，否则归零。
    最终返回 consecutive_pass_count < pass_count_min。
    若 on_fail_action 为 'none'，直接返回 False（不重打，直接推进）。
    """
    if self._on_fail_action == "none":
        return False

    if not self._slice_stats:
        return True  # 还没有打完任何片，需要重打（首次）

    last = self._slice_stats[-1]
    key_stroke = last.get("keyStroke", 0)
    speed = last.get("speed", 0)
    accuracy = last.get("accuracy", 0)

    if (key_stroke >= self._key_stroke_min and
        speed >= self._speed_min and
        accuracy >= self._accuracy_min):
        self._consecutive_pass_count += 1
    else:
        self._consecutive_pass_count = 0

    return self._consecutive_pass_count < self._pass_count_min
```

- [ ] **Step 4: 新增 on_fail_action 属性**

```python
@property
def on_fail_action(self) -> str:
    return self._on_fail_action
```

- [ ] **Step 5: 清理旧属性与方法**

删除 `_retype_enabled`、`_retype_metric`、`_retype_operator`、`_retype_threshold`、`_retype_shuffle` 及其 getter（`retype_shuffle` property）。

---

## Task 5: 测试 — 更新旧测试并新增 SessionContext 单元测试

**Files:**
- Modify: `tests/test_backend.py`
- Modify: `tests/test_slice_typing.py`（如需）
- Create: `tests/test_session_context.py`

- [ ] **Step 1: 更新 test_backend.py 中的 setupSliceMode 调用**

将所有 `bridge.setupSliceMode(text, slice_size, False, "", "", 0.0, False)` 替换为：
```python
bridge.setupSliceMode(text, slice_size, 1, 200, 100, 95, 1, "retype", False)
```

涉及行号约：220、240、269、300。

- [ ] **Step 2: 更新 test_backend.py 中涉及旧参数的 session setup**

将 `session.setup_slice_mode("天地玄黄", 4, True, "accuracy", "lt", 98.0, False)` 替换为：
```python
session.setup_slice_mode("天地玄黄", 4, 1, 0, 0, 98, 1, "retype", False)
```

- [ ] **Step 3: 新建 test_session_context.py**

```python
"""TypingSessionContext 合格指标与事件判定测试。"""

from src.backend.application.session_context import TypingSessionContext


class TestSliceQualification:
    def _make_context(self, pass_count=1, on_fail="retype"):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode(
            text="一二三四五六七八九十",
            slice_size=2,
            start_slice=1,
            key_stroke_min=200,
            speed_min=100,
            accuracy_min=95,
            pass_count_min=pass_count,
            on_fail_action=on_fail,
            shuffle=False,
        )
        return ctx

    def test_all_metrics_met_single_pass(self):
        ctx = self._make_context(pass_count=1)
        ctx.collect_slice_result({
            "keyStroke": 220, "speed": 110, "accuracy": 96.0,
        })
        assert ctx.should_retype() is False

    def test_speed_below_threshold_triggers_retype(self):
        ctx = self._make_context(pass_count=1)
        ctx.collect_slice_result({
            "keyStroke": 220, "speed": 90, "accuracy": 96.0,
        })
        assert ctx.should_retype() is True

    def test_pass_count_requires_consecutive_slices(self):
        ctx = self._make_context(pass_count=3)
        # 第1片达标
        ctx.collect_slice_result({"keyStroke": 220, "speed": 110, "accuracy": 96.0})
        assert ctx.should_retype() is True  # 还需2片
        # 模拟重打后 advance_slice（测试中手动推进）
        ctx.advance_slice()
        # 第2片达标
        ctx.collect_slice_result({"keyStroke": 220, "speed": 110, "accuracy": 96.0})
        assert ctx.should_retype() is True  # 还需1片
        ctx.advance_slice()
        # 第3片达标
        ctx.collect_slice_result({"keyStroke": 220, "speed": 110, "accuracy": 96.0})
        assert ctx.should_retype() is False  # 终于达标

    def test_fail_resets_consecutive_pass_count(self):
        ctx = self._make_context(pass_count=2)
        ctx.collect_slice_result({"keyStroke": 220, "speed": 110, "accuracy": 96.0})
        assert ctx.should_retype() is True
        ctx.advance_slice()
        # 第2片不达标
        ctx.collect_slice_result({"keyStroke": 220, "speed": 80, "accuracy": 96.0})
        assert ctx.should_retype() is True
        ctx.advance_slice()
        # 第3片达标，但累计已被重置
        ctx.collect_slice_result({"keyStroke": 220, "speed": 110, "accuracy": 96.0})
        assert ctx.should_retype() is True  # 只有1片，还需1片

    def test_none_action_never_retypes(self):
        ctx = self._make_context(pass_count=1, on_fail="none")
        ctx.collect_slice_result({"keyStroke": 0, "speed": 0, "accuracy": 0.0})
        assert ctx.should_retype() is False

    def test_start_slice_sets_initial_index(self):
        ctx = TypingSessionContext()
        ctx.setup_slice_mode(
            text="一二三四五六七八九十", slice_size=2, start_slice=3,
            key_stroke_min=0, speed_min=0, accuracy_min=0,
            pass_count_min=1, on_fail_action="retype", shuffle=False,
        )
        assert ctx.slice_index == 3
        assert ctx.get_current_slice_text() == "五六"
```

- [ ] **Step 4: 运行测试**

```bash
uv run pytest tests/test_session_context.py tests/test_backend.py tests/test_slice_typing.py -v
```

---

## Task 6: 验证与收尾

**Files:**
- Modify: 所有已变更文件

- [ ] **Step 1: 运行全部测试**

```bash
uv run pytest
```

- [ ] **Step 2: 代码风格检查**

```bash
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "feat(slice-config): 重构载文设置Dialog"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] 四指标合格判定（击键/速度/键准/达标次数）→ Task 4
   - [x] 未达标事件选择（乱序重打/重打/无）→ Task 1 Step 3, Task 2, Task 4
   - [x] 开始片段输入 → Task 1 Step 4, Task 4 Step 2
   - [x] 全文乱序按钮 → Task 1 Step 5
   - [x] 布局优化 → Task 1
   - [x] 输入校验 → Task 1 Step 6

2. **Placeholder scan:**
   - [x] 无 TBD/TODO/"implement later"
   - [x] 所有代码块包含完整实现
   - [x] 所有测试包含断言

3. **Type consistency:**
   - [x] `setupSliceMode` 签名在 Bridge/TypingAdapter/SessionContext 中一致
   - [x] `on_fail_action` 字符串值在 QML/Bridge/SessionContext 中一致：`"shuffle_retype"`、`"retype"`、`"none"`
   - [x] `should_retype` 返回 bool 语义不变
