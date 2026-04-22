# 打字会话状态机设计（TypingSessionContext）

## 1. 背景与目标

当前打字会话的状态散落在 Bridge（`_slice_mode`, `_slices`, `_current_slice`, `_text_id` 等）和 TypingAdapter（`_slice_index`）中，缺乏统一的推导关系。核心痛点：

1. **成绩提交资格判断分散**：`_submit_score_async` 仅检查 `text_id > 0`，但"分片不提交""乱序不提交"等规则隐含在各载文路径中（通过提前清零 text_id 实现），缺乏显式建模
2. **用户无法提前知道成绩能否提交**：只有打完后才发现成绩没提交，缺乏透明度
3. **延迟查询策略可优化**：当前剪贴板和分片/乱序路径也会触发无意义的 text_id 回查（虽然剪贴板因 source_key="" 实际不会触发回查，但逻辑分散不显式）

**目标**：引入集中式会话状态机，统一管理会话级别状态，自动推导成绩提交资格，QML 可实时展示资格原因。

## 2. 架构方案

**新建 `TypingSessionContext`（Application 层）**，持有四个正交状态维度，通过显式转换方法管理状态流转，自动推导成绩提交资格。

理由：状态机天然适合"载文模式"这种有明确阶段和转换约束的场景。放在 Application 层因为它纯推导业务规则（哪些场景可以提交成绩），不碰网络请求和 Qt 信号（text_id 回查仍由 TextAdapter/TypingAdapter 协调，状态机只接收结果）。

### 架构约束

- **TypingSessionContext 不发起网络请求**：text_id 的延迟回查仍由 `TextAdapter._lookup_text_id_async` 执行（daemon thread），回查完成后通过 `TypingAdapter.set_text_id()` → `TypingSessionContext.set_text_id()` 回填结果。状态机只做推导，不做 I/O。
- **Bridge 不直接操作 TypingSessionContext**：状态机的 `setup_*` 调用由 `TypingAdapter` 代理，Bridge 通过 TypingAdapter 间接触发。这保持 Presentation → Application 的依赖方向通过 Adapter 过渡。
- **不引入 NetworkMonitor**：网络状态检测需要额外 ping 请求，增加复杂度且收益有限。当前 text_id 回查失败时静默忽略，效果等同于 INELIGIBLE。离线判断留给 text_id 回查本身自然失败即可。

## 3. 状态空间

```python
class SessionPhase(Enum):
    IDLE = auto()       # 空闲
    READY = auto()      # 文本已加载，等待开始
    TYPING = auto()     # 正在打字
    COMPLETED = auto()  # 当前段（片或全文）已打完
    CLOSED = auto()     # 会话结束

class SourceMode(Enum):
    NETWORK = auto()    # 从服务端加载的标准来源（text_id 加载时即确定）
    LOCAL = auto()      # 从本地文件加载（text_id 需异步回查）
    CUSTOM = auto()     # loadFullText 路径（全文载入，source_key 可空，text_id 异步回查）
    CLIPBOARD = auto()  # 从剪贴板粘贴（无 source_key，不回查 text_id）
    SLICE = auto()      # 分片载文模式
    SHUFFLE = auto()    # 乱序模式

class UploadStatus(Enum):
    CONFIRMED = auto()  # 已确认可提交（有有效 text_id）
    PENDING = auto()    # 待确认（text_id 回查中）
    INELIGIBLE = auto() # 不符合提交条件
    NA = auto()         # 不适用（分片/乱序等本身就不提交）
```

### 关于 SourceMode 设计的说明

**为什么是 CUSTOM 而非 MANUAL？** 当前 `loadFullText(text, source_key="")` 是一个统一入口：
- 带 `source_key` 时（如从文本库选择）：走 `"custom"` lookup_key 异步回查 text_id，回查成功则有资格提交
- 不带 `source_key` 时（用户直接输入）：同样走 `"custom"` lookup_key 异步回查
- 两者都**可能**获得有效 text_id（取决于服务端是否存在匹配文本），因此不应在来源层面直接排除

当前代码中不存在"手动输入"与"文本库选择"的本质区分——它们走同一条 `loadFullText` 路径，都会尝试 text_id 回查。将 CUSTOM 和 CLIPBOARD 分开是因为剪贴板明确不触发回查（source_key="" 且 `load_from_clipboard` 不走 `_lookup_text_id_async`），而 CUSTOM 会。

**为什么删除 Integrity 维度？** 当前代码没有追踪文本是否被编辑过。SliceConfigDialog 中的 TextArea 确实可编辑，但编辑后的全文载入走 `loadFullText` 仍会尝试 text_id 回查——如果回查命中，当前行为是允许提交的。引入 `Integrity.EDITED → INELIGIBLE` 会改变当前行为，且当前没有编辑追踪机制。如果未来需要此功能，应作为独立需求单独设计追踪机制，而非在状态机中预留空维度。

### 关于 NetworkState 的说明

**不引入 NetworkState 维度**。原因：
1. NetworkMonitor 需要额外 ping 请求，与"减少网络请求"的目标矛盾
2. text_id 回查本身就是自然的网络探测——失败时效果等同于 INELIGIBLE
3. 当前架构中网络请求由 Adapter 层协调，Application 层不应管理网络状态
4. 如未来确实需要离线提示，应由 Presentation 层根据 text_id 回查结果推导，无需独立网络状态维度

## 4. 状态转换

```
IDLE --[setup_*_session]--> READY --[start_typing]--> TYPING --[complete_typing]--> COMPLETED --[reset/advance_slice]--> (IDLE | READY)
                                                         |
                                                         +--[exit/close]--> CLOSED
```

非法转换（如 `TYPING → READY`）在 `complete_typing()` / `reset()` 中通过断言或静默忽略防护。

## 5. 资格推导规则

在 `complete_typing()` 时自动推导 `UploadStatus`：

```python
def _derive_upload_status(self) -> UploadStatus:
    # 第一层：来源模式直接排除（无需 text_id）
    if self._source_mode in (SourceMode.SLICE, SourceMode.SHUFFLE,
                              SourceMode.CLIPBOARD):
        return UploadStatus.NA

    # 第二层：已有 text_id（无需回查）
    if self._text_id is not None and self._text_id > 0:
        return UploadStatus.CONFIRMED

    # 第三层：text_id 待回查
    if self._source_mode in (SourceMode.NETWORK, SourceMode.LOCAL,
                              SourceMode.CUSTOM):
        return UploadStatus.PENDING

    return UploadStatus.INELIGIBLE
```

### 推导说明

| 来源模式 | 加载时 text_id | 可能的 UploadStatus | 说明 |
|----------|---------------|---------------------|------|
| NETWORK | 由服务端返回，已确定 | CONFIRMED | 网络文本加载时 text_id 即已知 |
| LOCAL | None（需异步回查） | PENDING → CONFIRMED/INELIGIBLE | 本地文本通过 daemon thread 回查 |
| CUSTOM | None（需异步回查） | PENDING → CONFIRMED/INELIGIBLE | loadFullText 路径，回查可能命中 |
| CLIPBOARD | None（不回查） | NA | source_key="" 不触发回查 |
| SLICE | None（显式清零） | NA | 分片文本不提交 |
| SHUFFLE | None（显式清零） | NA | 乱序文本不提交 |

**关键差异**：NETWORK 来源的 text_id 在加载时即由服务端返回，因此 `complete_typing()` 时一定走到"第二层：已有 text_id"分支，返回 CONFIRMED。只有 LOCAL 和 CUSTOM 来源的 text_id 可能为 None，需要走 PENDING 路径等待回查结果。

### text_id 回查时序

text_id 回查不由状态机发起，而是复用现有的 `TextAdapter._lookup_text_id_async` 流程：

```
TextAdapter._on_text_loaded (或 lookup_text_id)
  → _lookup_text_id_async (daemon thread)
    → LoadTextUseCase.lookup_text_id()
      → TextSourceGateway.lookup_text_id()
        → 成功: localTextIdResolved.emit(text_id)
          → Bridge._on_local_text_id_resolved(text_id)
            → Bridge.setTextId(text_id)
              → TypingAdapter.setTextId(text_id)
                → TypingSessionContext.set_text_id(text_id)
                  → UploadStatus: PENDING → CONFIRMED
        → 失败: 静默忽略
          → UploadStatus 保持 PENDING（成绩不提交）
```

**PENDING 状态的实际处理**：当 `complete_typing()` 推导出 PENDING 时，`_submit_score_async` 检查 `can_submit_score()` 返回 False（PENDING ≠ CONFIRMED），成绩不提交。如果后续 text_id 回查成功，状态变为 CONFIRMED，但打字已结束，成绩不会补提。这是可接受的——本地/自定义文本的 text_id 回查是尽力而为，不保证及时完成。

### 零查询场景

| 场景 | UploadStatus | 是否触发网络请求 |
|------|-------------|----------------|
| 分片模式 | NA | 否 |
| 乱序模式 | NA | 否 |
| 剪贴板 | NA | 否 |
| 在线 + text_id 已知 | CONFIRMED | 否 |
| 在线 + text_id 未知 | PENDING（回查中） | 是（复用现有 daemon thread 回查，非状态机发起） |

### 资格原因消息

```python
def get_eligibility_reason(self) -> str:
    if self._source_mode in (SourceMode.SLICE, SourceMode.SHUFFLE):
        return "分片/乱序模式，成绩不提交排行榜"
    if self._source_mode == SourceMode.CLIPBOARD:
        return "剪贴板文本，成绩不提交排行榜"
    if self._upload_status == UploadStatus.CONFIRMED:
        return "成绩将提交排行榜"
    if self._upload_status == UploadStatus.PENDING:
        return "正在确认成绩提交资格..."
    return "成绩不提交排行榜"
```

## 6. 完整接口

```python
class TypingSessionContext:
    # 查询
    @property phase(self) -> SessionPhase
    @property source_mode(self) -> SourceMode
    @property upload_status(self) -> UploadStatus
    @property text_id(self) -> int | None
    @property slice_index(self) -> int | None
    @property slice_total(self) -> int | None

    def can_submit_score(self) -> bool
    def get_eligibility_reason(self) -> str

    # 设置（每种来源一个入口）
    def setup_network_session(self, text_id: int, source_key: str) -> None
    def setup_local_session(self, source_key: str, text_id: int | None = None) -> None
    def setup_custom_session(self, source_key: str) -> None
    def setup_clipboard_session(self) -> None
    def setup_slice_session(self, total: int) -> None
    def setup_shuffle_session(self) -> None

    # 阶段转换
    def start_typing(self) -> None
    def complete_typing(self) -> None
    def reset(self) -> None

    # 回调（由 Adapter 调用）
    def set_text_id(self, text_id: int | None) -> None
    def advance_slice(self) -> None

    # 订阅（由 Adapter 订阅，桥接到 Qt 信号）
    def subscribe_upload_status(self, callback: callable) -> None
    def subscribe_eligibility_reason(self, callback: callable) -> None
```

### 接口变更说明

- **`setup_custom_session(source_key)`**：替代原 `setup_manual_session`，对应 `loadFullText` 路径。不传 `original_content`——内容追踪不是状态机的职责，text_id 回查由 TextAdapter 协调。
- **`setup_slice_session(total)`**：只传总片数，不传 `list[str]`——切片数据和切片加载逻辑仍留在 Bridge（当前实现），状态机只关心模式标记和总数。
- **`setup_network_session(text_id, source_key)`**：网络来源加载时 text_id 已确定，直接传入。
- **删除 `mark_text_edited()`**：无编辑追踪机制支撑。
- **删除 `Integrity` 维度和 `NetworkState` 维度**。

## 7. 与现有组件的集成

### 7.1 TypingService — 不变

所有 `set_*`、`accumulate_*`、`handle_committed_text` 方法完全不变。`TypingState` 字段不变。

### 7.2 TypingAdapter — 注入 + 信号桥接

```python
class TypingAdapter(QObject):
    uploadStatusChanged = Signal(int)
    eligibilityReasonChanged = Signal(str)

    def __init__(self, ..., session_context: TypingSessionContext):
        self._session_context = session_context
        session_context.subscribe_upload_status(self._on_session_upload_status)
        session_context.subscribe_eligibility_reason(self._on_session_reason)
```

**新增代理方法**（Bridge 通过这些方法间接触发状态机，而非直接操作 session_context）：

```python
def setup_network_session(self, text_id: int, source_key: str) -> None:
    self._session_context.setup_network_session(text_id, source_key)

def setup_local_session(self, source_key: str, text_id: int | None = None) -> None:
    self._session_context.setup_local_session(source_key, text_id)

# ... 其他 setup_* 代理方法类似
```

`_check_typing_complete` 新增一行：
```python
self._session_context.complete_typing()
```

`_submit_score_async` 改为读状态机：
```python
if not self._session_context.can_submit_score():
    return
text_id = self._session_context.text_id
```

`setTextId` 同步更新状态机：
```python
def setTextId(self, text_id: int | None) -> None:
    self._typing_service.set_text_id(text_id)
    self._session_context.set_text_id(text_id)  # 新增
```

### 7.3 Bridge — 载文方法通过 TypingAdapter 更新状态机

```python
def loadFullText(self, text, source_key=""):
    # ... 现有逻辑 ...
    self._typing_adapter.setup_custom_session(source_key or "custom")

def setupSliceMode(self, text, ...):
    # ... 分片逻辑 ...
    self._typing_adapter.setup_slice_session(len(self._slices))

def requestShuffle(self):
    # ... 现有逻辑 ...
    self._typing_adapter.setup_shuffle_session()

def loadTextFromClipboard(self):
    # ... 现有逻辑 ...
    self._typing_adapter.setup_clipboard_session()
```

**关键**：Bridge 不直接持有 `session_context` 引用，通过 `_typing_adapter` 代理调用。保持 Presentation → Application 的依赖方向通过 Adapter 过渡。

### 7.4 TextAdapter — textLoaded 信号链不变

`TextAdapter._on_text_loaded()` 和 `_lookup_text_id_async()` 的逻辑完全不变。当 text_id 回查成功时，现有信号链 `localTextIdResolved` → `Bridge.setTextId()` → `TypingAdapter.setTextId()` → `TypingSessionContext.set_text_id()` 自动更新状态机。

### 7.5 QML 展示

新增 `uploadStatus` / `eligibilityReason` 属性绑定，在 ScoreArea 旁显示状态标签。

## 8. 依赖注入（main.py）

```text
TypingSessionContext()
  → TypingAdapter(typing_service, score_gateway, score_submitter, session_context)
    → Bridge(typing_adapter, text_adapter, ...)
```

新增一步装配：创建 `TypingSessionContext`（无外部依赖），注入 `TypingAdapter`。

**对比原方案**：移除了 `NetworkMonitor` 和 `TextIdFetcher` 的装配步骤——这两个组件不再需要，text_id 回查复用现有 `TextAdapter` + daemon thread 机制。

## 9. 测试策略

### 单元测试（纯 Python，不需要 Qt）

| 测试 | 验证 |
|------|------|
| `test_network_session_confirmed` | 网络来源 + text_id 已知 → CONFIRMED |
| `test_local_session_with_text_id` | 本地来源 + text_id 已回查 → CONFIRMED |
| `test_local_session_pending` | 本地来源 + text_id 未回查 → PENDING |
| `test_custom_session_pending` | CUSTOM 来源 + text_id 未回查 → PENDING |
| `test_custom_session_resolved` | CUSTOM 来源 + text_id 回查成功 → CONFIRMED |
| `test_slice_mode_na` | 分片 → NA |
| `test_shuffle_mode_na` | 乱序 → NA |
| `test_clipboard_mode_na` | 剪贴板 → NA |
| `test_set_text_id_transitions` | PENDING + set_text_id(>0) → CONFIRMED |
| `test_eligibility_reason_messages` | 每种状态返回正确的中文消息 |
| `test_phase_transitions` | IDLE→READY→TYPING→COMPLETED→IDLE |
| `test_can_submit_score` | 只有 CONFIRMED 时 can_submit_score() 为 True |
| `test_advance_slice` | 分片模式下 advance_slice 更新 slice_index |

## 10. 迁移策略（渐进式）

1. **Phase 1**：引入 `TypingSessionContext`，旧逻辑暂保留
2. **Phase 2**：TypingAdapter 新增 setup_* 代理方法，Bridge 载文方法同时更新状态机 + 旧状态
3. **Phase 3**：`_submit_score_async` 改为读状态机 `can_submit_score()`
4. **Phase 4**：验证所有场景后，移除 Bridge 中的冗余载文状态字段（`_text_id` 等，由状态机接管）

## 11. 改动范围

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/backend/application/session_context.py` | 新建 | 状态机（纯推导，无 I/O） |
| `src/backend/presentation/adapters/typing_adapter.py` | 修改 | 注入 session_context, 新增信号, 新增 setup_* 代理方法, 修改两个方法 |
| `src/backend/presentation/bridge.py` | 修改 | 载文方法调用 TypingAdapter.setup_* 更新状态机, 新增信号转发 |
| `src/qml/pages/TypingPage.qml` | 修改 | 绑定 uploadStatus / eligibilityReason |
| `main.py` | 修改 | 装配一步 |
| `tests/test_session_context.py` | 新建 | 单元测试 |
| `docs/ARCHITECTURE.md` | 修改 | 新增状态机章节 |

**不改动**：TypingService, TypingState, TextAdapter, TextSourceGateway, LoadTextUseCase, ScoreGateway, workers/, SliceConfigDialog.qml

## 12. 原方案修正记录

| # | 原方案内容 | 问题 | 修正 |
|---|-----------|------|------|
| 1 | `SourceMode.MANUAL` 和 `SourceMode.CLIPBOARD` 分开，两者都返回 `NA` | `loadFullText(source_key="")` 也会尝试 text_id 回查，可能获得有效 text_id 有资格提交。MANUAL 不应直接排除 | 合并为 `SourceMode.CUSTOM`，推导为 PENDING（等回查结果）而非 NA |
| 2 | `Integrity.EDITED → INELIGIBLE` | 当前没有编辑追踪机制。`loadFullText` 编辑后的文本仍会回查 text_id，回查成功当前允许提交 | 删除 Integrity 维度，待有追踪机制时再引入 |
| 3 | `NetworkMonitor` + `TextIdFetcher` 放在 Application 层 | Application 层不应发起网络请求/管理线程。且 NetworkMonitor 的 ping 是多余的——text_id 回查失败本身等效于 INELIGIBLE | 删除 NetworkMonitor 和 TextIdFetcher，text_id 回查复用现有 TextAdapter daemon thread 机制 |
| 4 | Bridge 直接调用 `session_context.setup_*_session()` | 违反 Presentation → Application 依赖方向（应通过 Adapter 过渡） | Bridge 通过 `TypingAdapter.setup_*()` 代理方法间接触发状态机 |
| 5 | `setup_slice_session(slices: list[str])` | 切片数据和加载逻辑在 Bridge 中，状态机不需要持有切片内容 | 改为 `setup_slice_session(total: int)`，只传总片数 |
| 6 | `NetworkState` 维度 + 离线判断 | NetworkState 需要网络探测，与减少网络请求的目标矛盾。回查失败自然等效 INELIGIBLE | 删除 NetworkState 维度 |
| 7 | "当前无论什么来源都会尝试 lookup_text_id" | 不准确。剪贴板 `source_key=""` 不触发回查（`if text_id is None and source_key` 守卫）；分片/乱序显式清零 text_id | 修正痛点描述：问题不是"都会触发"，而是"规则隐含不显式" |
