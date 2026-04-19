# 薄弱字自定义排序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将薄弱字页面的硬编码排序逻辑（`error_count / char_count DESC`）改为用户可选择的多维排序，支持按错误率、按错误次数、按加权评分排序，且加权评分的权重可由用户自定义调节。

**Architecture:** 在现有链路 `WeakCharsPage → Bridge.loadWeakChars → CharStatsAdapter → WeakCharsQueryWorker → CharStatsService → SqliteCharStatsRepository` 中，每一层增加 `sort_mode` 参数透传。Repository 层新增 `get_chars_by_sort(sort_mode, weights, n)` 方法，根据 sort_mode 构造不同的 ORDER BY 子句。QML 层新增排序模式选择器 UI（ComboBox + 权重滑块）。

**Tech Stack:** Python/PySide6, QML (RinUI), SQLite, 现有 Worker/Adapter/Service/Repository 分层架构

---

## 现状分析

**当前问题**：`WeakCharsPage.qml` 调用 `appBridge.loadWeakChars()` 无任何排序参数。整条链路（Bridge → Adapter → Worker → Service → Repository）硬编码 `ORDER BY CAST(error_char_count AS REAL) / char_count DESC`。用户无法选择按错误次数或其他维度排序。

**当前数据**：SQLite `char_stats` 表有 702 个字符，其中 221 个有错误记录。字段：
```
char (PK), char_count, error_char_count, total_ms, min_ms, max_ms, last_seen, last_synced_at, is_dirty
```

**排序选项设计**：
| Sort Mode | SQL ORDER BY | 含义 |
|-----------|-------------|------|
| `error_rate` | `CAST(error_char_count AS REAL) / char_count DESC` | 错误率高优先 |
| `error_count` | `error_char_count DESC` | 错错次数多优先 |
| `weighted` | `pow(err_rate, W1) * pow(log(char_count+1), W2) * pow(log(err_count+1), W3) DESC` | 加权评分（W1/W2/W3 可调） |

**默认权重**：error_rate=0.6, total_count=0.2, error_count=0.2（偏重错误率，兼顾出现频率和绝对错误量）

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/backend/domain/ports/char_stats_repository.py` | Modify | CharStatsRepository ABC 新增 `get_chars_by_sort()` 抽象方法 |
| `src/backend/infrastructure/sqlite_char_stats_repository.py` | Modify | 实现 `get_chars_by_sort()`，按 sort_mode 构造 SQL |
| `src/backend/domain/services/char_stats_service.py` | Modify | `get_weakest_chars()` 接受 sort_mode + weights 参数，传给 repo |
| `src/backend/workers/weak_chars_query_worker.py` | Modify | 任务函数接受 sort_mode + weights，传给 service |
| `src/backend/presentation/adapters/char_stats_adapter.py` | Modify | `loadWeakChars()` 接受 sort_mode + weights，传给 worker |
| `src/backend/presentation/bridge.py` | Modify | `loadWeakChars()` 接受 sort_mode + weights，传给 adapter |
| `src/qml/pages/WeakCharsPage.qml` | Modify | 新增排序模式 ComboBox + 权重调节 UI + typingEnded 自动刷新 |
| `tests/test_char_stats_sorting.py` | Create | 测试各种排序模式的正确性 |

---

### Task 1: Repository 层 — 新增 `get_chars_by_sort()` 方法

**Files:**
- Modify: `src/backend/domain/ports/char_stats_repository.py:27-37`
- Modify: `src/backend/infrastructure/sqlite_char_stats_repository.py:55-77`

- [ ] **Step 1.1: 修改 Port 抽象类**

在 `CharStatsRepository` ABC 中新增抽象方法：

```python
@abc.abstractmethod
def get_chars_by_sort(
    self,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
    n: int = 10,
) -> list[CharStat]:
    """按指定排序模式获取薄弱字列表。

    Args:
        sort_mode: 排序模式 — "error_rate" | "error_count" | "weighted"
        weights: weighted 模式的权重 {"error_rate": float, "total_count": float, "error_count": float}
        n: 返回数量
    """
```

- [ ] **Step 1.2: 实现 Repository 方法**

在 `SqliteCharStatsRepository` 中新增方法：

```python
def get_chars_by_sort(
    self,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
    n: int = 10,
) -> list[CharStat]:
    if sort_mode == "error_rate":
        order_by = "CAST(error_char_count AS REAL) / char_count DESC"
    elif sort_mode == "error_count":
        order_by = "error_char_count DESC"
    elif sort_mode == "weighted":
        w = weights or {}
        w_rate = float(w.get("error_rate", 0.6))
        w_total = float(w.get("total_count", 0.2))
        w_err = float(w.get("error_count", 0.2))
        order_by = (
            f"POWER(CAST(error_char_count AS REAL) / MAX(char_count, 1), {w_rate}) "
            f"* POWER(LOG(MAX(char_count, 1) + 1), {w_total}) "
            f"* POWER(LOG(MAX(error_char_count, 0) + 1), {w_err}) DESC"
        )
    else:
        order_by = "CAST(error_char_count AS REAL) / char_count DESC"

    rows = self._conn.execute(
        f"SELECT * FROM char_stats WHERE char_count > 0 ORDER BY {order_by} LIMIT ?",
        (n,),
    ).fetchall()
    return [self._row_to_entity(r) for r in rows]
```

- [ ] **Step 1.3: 保留旧方法为兼容层**

`get_weakest_chars()` 改为委托到新方法：

```python
def get_weakest_chars(self, n: int = 10) -> list[CharStat]:
    return self.get_chars_by_sort("error_rate", None, n)
```

---

### Task 2: Service 层 — 透传排序参数

**Files:**
- Modify: `src/backend/domain/services/char_stats_service.py:94-103`

- [ ] **Step 2.1: 修改 `get_weakest_chars()` 签名**

```python
def get_weakest_chars(
    self,
    n: int = 10,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
) -> list[dict[str, int | float]]:
    if not self._repo.exists():
        return []
    stats = self._repo.get_chars_by_sort(sort_mode, weights, n)
    return [s.to_dict() for s in stats]
```

- [ ] **Step 2.2: 验证旧调用点不受影响**

旧调用 `get_weakest_chars(10)` 不传 sort_mode，使用默认值 `"error_rate"`，行为与原来一致。

---

### Task 3: Worker 层 — 透传排序参数

**Files:**
- Modify: `src/backend/workers/weak_chars_query_worker.py:10-12`

- [ ] **Step 3.1: 修改任务函数签名**

```python
def _query_weak_chars_task(
    char_stats_service: CharStatsService,
    n: int = 10,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
) -> list[dict[str, int | float]]:
    return char_stats_service.get_weakest_chars(n, sort_mode, weights)
```

- [ ] **Step 3.2: 修改构造函数**

```python
class WeakCharsQueryWorker(BaseWorker):
    def __init__(
        self,
        char_stats_service: CharStatsService,
        n: int = 10,
        sort_mode: str = "error_rate",
        weights: dict | None = None,
    ):
        super().__init__(
            _query_weak_chars_task,
            char_stats_service=char_stats_service,
            n=n,
            sort_mode=sort_mode,
            weights=weights,
        )
```

---

### Task 4: Adapter 层 — 透传排序参数

**Files:**
- Modify: `src/backend/presentation/adapters/char_stats_adapter.py:25-33`

- [ ] **Step 4.1: 修改 `loadWeakChars()` 签名**

```python
@Slot()
def loadWeakChars(
    self,
    n: int = 10,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
) -> None:
    if not self._char_stats_service:
        self.weakestCharsLoaded.emit([])
        return
    worker = WeakCharsQueryWorker(
        self._char_stats_service,
        n=n,
        sort_mode=sort_mode,
        weights=weights,
    )
    worker.signals.succeeded.connect(self._on_weak_chars_loaded)
    worker.signals.failed.connect(lambda msg: log_info(f"[CharStatsAdapter] {msg}"))
    QThreadPool.globalInstance().start(worker)
```

- [ ] **Step 4.2: 修改 `loadWeakChars()` 签名为完整版**

```python
@Slot()
def loadWeakChars(
    self,
    n: int = 10,
    sort_mode: str = "error_rate",
    weights: dict | None = None,
) -> None:
    if not self._char_stats_service:
        self.weakestCharsLoaded.emit([])
        return
    worker = WeakCharsQueryWorker(
        self._char_stats_service,
        n=n,
        sort_mode=sort_mode,
        weights=weights,
    )
    worker.signals.succeeded.connect(self._on_weak_chars_loaded)
    worker.signals.failed.connect(lambda msg: log_info(f"[CharStatsAdapter] {msg}"))
    QThreadPool.globalInstance().start(worker)
```

---

### Task 5: Bridge 层 — 透传排序参数到 QML

**Files:**
- Modify: `src/backend/presentation/bridge.py:140-141`

- [ ] **Step 5.1: 修改 `loadWeakChars()` Slot**

```python
@Slot(int, str, "QVariantMap")
def loadWeakChars(self, n=10, sortMode="error_rate", weights=None):
    self._char_stats_adapter.loadWeakChars(
        n=n,
        sort_mode=sortMode,
        weights=weights if weights else None,
    )
```

**注意**：QML 传 QVariantMap 到 Python 后自动转为 dict。旧调用 `appBridge.loadWeakChars()` 不传参时，`n=10`、`sortMode="error_rate"`、`weights=None`，行为不变。

---

### Task 6: QML 层 — 排序模式选择器 UI

**Files:**
- Modify: `src/qml/pages/WeakCharsPage.qml`

- [ ] **Step 6.1: 新增排序状态属性**

```qml
property string sortBy: "error_rate"
property var sortWeights: ({ "error_rate": 0.6, "total_count": 0.2, "error_count": 0.2 })
```

- [ ] **Step 6.2: 在标题下方、Repeater 上方插入排序模式选择器**

```qml
// 标题下方，Repeater 之前插入
RowLayout {
    width: parent.width
    spacing: 8

    Text {
        text: qsTr("排序方式")
        typography: Typography.Body
        color: Theme.currentTheme.colors.textSecondaryColor
    }

    ComboBox {
        id: sortModeCombo
        Layout.preferredWidth: 140
        model: ListModel {
            id: sortModeModel
            ListElement { text: "按错误率"; value: "error_rate" }
            ListElement { text: "按错误次数"; value: "error_count" }
            ListElement { text: "加权评分"; value: "weighted" }
        }
        textRole: "text"
        valueRole: "value"
        currentIndex: 0
        onActivated: {
            sortBy = sortModeModel.get(currentIndex).value;
            weightPanel.visible = (sortBy === "weighted");
            reloadWeakChars();
        }
    }

    Item { Layout.fillWidth: true }
}

// 权重调节面板（默认隐藏，RinUI 无 Slider/SpinBox，用 ComboBox 选权重）
RowLayout {
    id: weightPanel
    visible: false
    width: parent.width
    spacing: 12

    // 错误率权重
    RowLayout {
        spacing: 4
        Text {
            text: "错误率"
            color: Theme.currentTheme.colors.textPrimary
            font.pixelSize: 12
        }
        ComboBox {
            id: errorRateWeight
            Layout.preferredWidth: 56
            model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
            currentIndex: 6  // 0.6
            onActivated: {
                sortWeights.error_rate = parseFloat(model[index]);
                reloadWeakChars();
            }
        }
    }
    // 出现频率权重
    RowLayout {
        spacing: 4
        Text {
            text: "出现频率"
            color: Theme.currentTheme.colors.textPrimary
            font.pixelSize: 12
        }
        ComboBox {
            id: totalCountWeight
            Layout.preferredWidth: 56
            model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
            currentIndex: 2  // 0.2
            onActivated: {
                sortWeights.total_count = parseFloat(model[index]);
                reloadWeakChars();
            }
        }
    }
    // 错误次数权重
    RowLayout {
        spacing: 4
        Text {
            text: "错误次数"
            color: Theme.currentTheme.colors.textPrimary
            font.pixelSize: 12
        }
        ComboBox {
            id: errorCountWeight
            Layout.preferredWidth: 56
            model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
            currentIndex: 2  // 0.2
            onActivated: {
                sortWeights.error_count = parseFloat(model[index]);
                reloadWeakChars();
            }
        }
    }
}
```
```

**注意**：RinUI 无 Slider/SpinBox 组件。权重调节改用 ComboBox 选择 0~1 的离散值（步长 0.1）。每个权重一个 ComboBox，水平排列。

- [ ] **Step 6.4: 抽取 `reloadWeakChars()` 函数**

```qml
function reloadWeakChars() {
    if (appBridge) {
        var w = sortBy === "weighted" ? sortWeights : null;
        appBridge.loadWeakChars(10, sortBy, w);
    }
}
```

- [ ] **Step 6.5: 统一所有调用点使用 `reloadWeakChars()`**

`StackView.onActivated` 中改为调用 `reloadWeakChars()`。

- [ ] **Step 6.6: 新增 `typingEnded` 自动刷新**

在 Connections 中新增对 `typingEnded` 的监听，打字结束自动刷新薄弱字列表（此时 CharStats 已 flush 到 SQLite）：

```qml
Connections {
    target: appBridge
    function onWeakestCharsLoaded(data) {
        weakCharsModel.clear();
        for (var i = 0; i < data.length; i++) {
            weakCharsModel.append(data[i]);
        }
    }
    function onTypingEnded() {
        // 打字结束、CharStats 已持久化后，自动刷新薄弱字
        reloadWeakChars();
    }
}
```

- [ ] **Step 6.7: 移除 `loadedOnce` 属性**

原来的 `loadedOnce` 防止重复加载，但有了排序切换后需要允许重复加载。保留 `StackView.onActivated` 调用（每次激活都刷新），移除 `loadedOnce` 守卫：

```qml
StackView.onActivated: {
    if (appBridge) {
        reloadWeakChars();
    }
}
```

---

### Task 7: 测试 — 排序模式正确性

**Files:**
- Create: `tests/test_char_stats_sorting.py`

- [ ] **Step 7.1: 测试 fixture — 插入已知数据**

```python
@pytest.fixture
def populated_repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    repo = SqliteCharStatsRepository(db_path)
    # 插入不同特征的字符
    test_data = [
        # char, char_count, error_char_count, total_ms
        ("A", 100, 50, 10000.0),   # 50% 错误率, 50次错
        ("B", 1000, 10, 50000.0),  # 1% 错误率, 10次错
        ("C", 10, 10, 5000.0),     # 100% 错误率, 10次错
        ("D", 500, 100, 30000.0),  # 20% 错误率, 100次错
        ("E", 5, 1, 2000.0),       # 20% 错误率, 1次错
    ]
    for char, cc, ecc, tms in test_data:
        repo.upsert(CharStat(char=char, char_count=cc, error_char_count=ecc,
                              total_ms=tms, min_ms=1.0, max_ms=100.0,
                              last_seen="2026-01-01"))
    return repo
```

- [ ] **Step 7.2: 测试 `error_rate` 排序**

```python
def test_sort_by_error_rate(populated_repo):
    result = populated_repo.get_chars_by_sort("error_rate", n=5)
    rates = [r.error_char_count / r.char_count for r in result]
    # C=100%, A=50%, D=20%, E=20%, B=1%
    assert result[0].char == "C"
    assert result[1].char == "A"
    assert rates == sorted(rates, reverse=True)
```

- [ ] **Step 7.3: 测试 `error_count` 排序**

```python
def test_sort_by_error_count(populated_repo):
    result = populated_repo.get_chars_by_sort("error_count", n=5)
    counts = [r.error_char_count for r in result]
    # D=100, A=50, B=10, C=10, E=1
    assert result[0].char == "D"
    assert counts == sorted(counts, reverse=True)
```

- [ ] **Step 7.4: 测试 `weighted` 排序**

```python
def test_sort_by_weighted(populated_repo):
    weights = {"error_rate": 0.6, "total_count": 0.2, "error_count": 0.2}
    result = populated_repo.get_chars_by_sort("weighted", weights, n=5)
    assert len(result) == 5
    # 验证排序是确定性的（同一权重多次调用结果一致）
    result2 = populated_repo.get_chars_by_sort("weighted", weights, n=5)
    assert [r.char for r in result] == [r.char for r in result2]
```

- [ ] **Step 7.5: 测试旧接口兼容**

```python
def test_get_weakest_chars_backward_compat(populated_repo):
    result = populated_repo.get_weakest_chars(3)
    assert len(result) == 3
    # 应与 error_rate 排序结果一致
    result_rate = populated_repo.get_chars_by_sort("error_rate", n=3)
    assert [r.char for r in result] == [r.char for r in result_rate]
```

- [ ] **Step 7.6: 运行测试**

```bash
cd /home/wangyu/work/typetype && python -m pytest tests/test_char_stats_sorting.py -v
```

---

### Task 8: 同步更新 AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 8.1: 更新薄弱字查询链路文档**

将 Chain 中的 `get_weakest_chars(10)` 更新为 `get_weakest_chars(n, sort_mode, weights)`，并说明排序参数沿链路透传。

- [ ] **Step 8.2: 补充 CharStatsRepository 接口说明**

在 Repository 端口说明中新增 `get_chars_by_sort()` 方法。

---

## 执行顺序

1. **Task 1** (Repository) — 基础层，不可跳过
2. **Task 2** (Service) — 依赖 Task 1
3. **Task 3** (Worker) — 依赖 Task 2
4. **Task 4** (Adapter) — 依赖 Task 3
5. **Task 5** (Bridge) — 依赖 Task 4
6. **Task 7** (测试) — 可在 Task 1-2 后立即编写并运行，验证底层逻辑
7. **Task 6** (QML) — 依赖 Task 5，最后做（UI 变更最易出 RinUI 兼容问题）
8. **Task 8** (文档) — 最后更新

---

## Self-Review Checklist

- [ ] 所有旧调用 `appBridge.loadWeakChars()` 和 `char_stats_service.get_weakest_chars(10)` 不传 sort_mode 时行为完全不变（默认 "error_rate" = 原 SQL）
- [ ] QML ComboBox 的 `sortBy` 属性与 Python 端 sort_mode 字符串值一致
- [ ] 加权评分公式在 SQLite 中的 `POWER` 和 `LOG` 函数可用（SQLite ≥ 3.35 内置数学函数）
- [ ] RinUI 无 Slider/SpinBox，权重调节改用 ComboBox 选 0~1 离散值（步长 0.1）
- [ ] StackView 生命周期：onActivated 中用 `Qt.callLater(reloadWeakChars)` 延迟触发
- [ ] 测试覆盖三种排序模式 + 旧接口兼容
