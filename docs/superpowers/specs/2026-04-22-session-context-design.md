# 打字会话状态机设计（TypingSessionContext）

## 1. 背景与目标

当前打字会话的状态散落在 Bridge（`_slice_mode`, `_slices`, `_current_slice`, `_text_id` 等）和 TypingAdapter（`_slice_index`）中，缺乏统一的推导关系。核心痛点：

1. **成绩提交资格判断分散**：`_submit_score_async` 仅检查 `text_id > 0`，但"分片不提交""编辑过不提交""离线不提交"等规则散落在各处
2. **用户无法提前知道成绩能否提交**：只有打完后才发现成绩没提交，缺乏透明度
3. **文本完整性无法追踪**：SliceConfigDialog 允许用户编辑 TextArea 中的原文，但编辑后的文本不应提交到排行榜
4. **延迟查询策略缺失**：当前无论什么来源都会尝试 `lookup_text_id`，分片/乱序/编辑过的文本也会触发无意义的网络请求

**目标**：引入集中式会话状态机，统一管理会话级别状态，自动推导成绩提交资格，延迟查询减少网络请求，QML 可实时展示资格原因。

## 2. 架构方案

**新建 `TypingSessionContext`（Application 层）**，持有五个正交状态维度，通过显式转换方法管理状态流转，自动推导成绩提交资格。

理由：状态机天然适合"载文模式"这种有明确阶段和转换约束的场景。放在 Application 层因为需要访问网络状态和 text_id 查询（业务编排），但不碰 Qt 信号（由 Adapter/Bridge 包装）。

## 3. 状态空间

```python
class SessionPhase(Enum):
    IDLE = auto()       # 空闲
    READY = auto()      # 文本已加载，等待开始
    TYPING = auto()     # 正在打字
    COMPLETED = auto()  # 当前段（片或全文）已打完
    CLOSED = auto()     # 会话结束

class SourceMode(Enum):
    NETWORK = auto()    # 从服务端加载的标准来源
    LOCAL = auto()      # 从本地文件加载
    CLIPBOARD = auto()  # 从剪贴板粘贴
    MANUAL = auto()     # 用户在 Dialog 中手动输入/编辑
    SLICE = auto()      # 分片载文模式
    SHUFFLE = auto()    # 乱序模式

class Integrity(Enum):
    ORIGINAL = auto()   # 与原文完全一致
    EDITED = auto()     # 用户编辑过

class UploadStatus(Enum):
    PENDING = auto()    # 待确认（需回查 text_id）
    CONFIRMED = auto()  # 已确认可提交（有有效 text_id）
    INELIGIBLE = auto()  # 不符合提交条件
    NA = auto()         # 不适用（分片/乱序等本身就不提交）

class NetworkState(Enum):
    UNKNOWN = auto()
    ONLINE = auto()
    OFFLINE = auto()
```

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
    # 第一层：来源模式直接排除
    if self._source_mode in (SourceMode.SLICE, SourceMode.SHUFFLE,
                              SourceMode.CLIPBOARD, SourceMode.MANUAL):
        return UploadStatus.NA

    # 第二层：完整性检查
    if self._integrity == Integrity.EDITED:
        return UploadStatus.INELIGIBLE

    # 第三层：已有 text_id（无需网络）
    if self._text_id is not None and self._text_id > 0:
        return UploadStatus.CONFIRMED

    # 第四层：离线
    if self._network_state == NetworkState.OFFLINE:
        return UploadStatus.INELIGIBLE

    # 第五层：需要延迟查询
    if self._source_mode in (SourceMode.NETWORK, SourceMode.LOCAL):
        self._schedule_text_id_lookup()
        return UploadStatus.PENDING

    return UploadStatus.INELIGIBLE
```

### 零查询场景

| 场景 | UploadStatus | 是否触发网络请求 |
|------|-------------|----------------|
| 分片模式 | NA | 否 |
| 乱序模式 | NA | 否 |
| 剪贴板 | NA | 否 |
| 手动输入 | NA | 否 |
| 编辑过 | INELIGIBLE | 否 |
| 离线 + text_id 未知 | INELIGIBLE | 否 |
| 离线 + text_id 已知 | CONFIRMED | 否 |
| 在线 + text_id 已知 | CONFIRMED | 否 |
| 在线 + text_id 未知 | PENDING → 查询 | 是（仅此一种） |

### 资格原因消息

```python
def get_eligibility_reason(self) -> str:
    if self._source_mode in (SourceMode.SLICE, SourceMode.SHUFFLE):
        return "分片/乱序模式，成绩不提交排行榜"
    if self._source_mode == SourceMode.CLIPBOARD:
        return "剪贴板文本，成绩不提交排行榜"
    if self._source_mode == SourceMode.MANUAL:
        return "手动输入文本，成绩不提交排行榜"
    if self._integrity == Integrity.EDITED:
        return "文本已修改，成绩不提交排行榜"
    if self._upload_status == UploadStatus.CONFIRMED:
        return "成绩将提交排行榜"
    if self._upload_status == UploadStatus.PENDING:
        return "正在确认成绩提交资格..."
    if self._network_state == NetworkState.OFFLINE:
        return "网络不可用，成绩暂不提交"
    return "成绩不提交排行榜"
```

## 6. 延迟查询

### 6.1 TextIdFetcher

按内容 hash 回查 text_id，带内存缓存：

```python
class TextIdFetcher:
    def __init__(self, text_source_gateway: TextSourceGateway):
        self._gateway = text_source_gateway
        self._cache: dict[str, int | None] = {}

    def lookup_async(self, source_key: str, content: str, callback: callable) -> None:
        cache_key = f"{source_key}:{hashlib.md5(content.encode()).hexdigest()}"
        if cache_key in self._cache:
            callback(self._cache[cache_key])
            return
        # daemon thread 查询，完成后 callback(text_id)
```

### 6.2 NetworkMonitor

轻量网络状态检测：

```python
class NetworkMonitor:
    def __init__(self, api_client: ApiClient | None):
        self._api_client = api_client
        self._state = NetworkState.UNKNOWN

    def check_async(self, callback: callable) -> None:
        # daemon thread ping，完成后 callback(NetworkState)
```

### 6.3 查询时序

```
complete_typing()
  → _derive_upload_status()
    → PENDING
      → NetworkMonitor.check_async()
        → ONLINE:
            → TextIdFetcher.lookup_async()
              → 找到: callback(text_id) → UploadStatus.CONFIRMED
              → 未找到: callback(None) → UploadStatus.INELIGIBLE
        → OFFLINE:
            → UploadStatus.INELIGIBLE（零查询）
```

离线时不发任何网络请求，直接 INELIGIBLE。

## 7. 完整接口

```python
class TypingSessionContext:
    # 查询
    @property phase(self) -> SessionPhase
    @property source_mode(self) -> SourceMode
    @property integrity(self) -> Integrity
    @property upload_status(self) -> UploadStatus
    @property text_id(self) -> int | None
    @property slice_index(self) -> int | None
    @property slice_total(self) -> int | None

    def can_submit_score(self) -> bool
    def get_eligibility_reason(self) -> str

    # 设置（每种来源一个入口）
    def setup_network_session(self, text_id: int, source_key: str, original_content: str) -> None
    def setup_local_session(self, source_key: str, original_content: str, text_id: int | None = None, integrity: Integrity = Integrity.ORIGINAL) -> None
    def setup_clipboard_session(self) -> None
    def setup_manual_session(self, text: str) -> None
    def setup_slice_session(self, slices: list[str]) -> None
    def setup_shuffle_session(self, shuffled: str) -> None

    # 阶段转换
    def start_typing(self) -> None
    def complete_typing(self) -> None
    def reset(self) -> None

    # 回调
    def set_text_id(self, text_id: int | None) -> None
    def mark_text_edited(self) -> None
    def advance_slice(self) -> None

    # 订阅
    def subscribe_upload_status(self, callback: callable) -> None
    def subscribe_eligibility_reason(self, callback: callable) -> None
```

## 8. 与现有组件的集成

### 8.1 TypingService — 不变

所有 `set_*`、`accumulate_*`、`handle_committed_text` 方法完全不变。`TypingState` 字段不变。

### 8.2 TypingAdapter — 注入 + 信号桥接

```python
class TypingAdapter(QObject):
    uploadStatusChanged = Signal(int)
    eligibilityReasonChanged = Signal(str)

    def __init__(self, ..., session_context: TypingSessionContext):
        self._session_context = session_context
        session_context.subscribe_upload_status(self._on_session_upload_status)
        session_context.subscribe_eligibility_reason(self._on_session_reason)
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

### 8.3 Bridge — 载文方法调用状态机

```python
def loadFullText(self, text, source_key=""):
    # ... 现有逻辑 ...
    self._session_context.setup_local_session(
        source_key or "manual", text,
        integrity=Integrity.EDITED if source_key == "" else Integrity.ORIGINAL
    )

def setupSliceMode(self, text, ...):
    # ... 分片逻辑 ...
    self._session_context.setup_slice_session(self._slices)

def requestShuffle(self):
    # ... 现有逻辑 ...
    self._session_context.setup_shuffle_session(shuffled)

def loadTextFromClipboard(self):
    # ... 现有逻辑 ...
    self._session_context.setup_clipboard_session()
```

### 8.4 SliceConfigDialog — 传递 isEdited

QML 中检测 TextArea 内容是否被编辑：
- 从文本库选择 → 记录原文
- 比较当前 TextArea 内容与原文
- `startSliceTyping()` 时传递 `isEdited` 标志给 Bridge

### 8.5 QML 展示

新增 `uploadStatus` / `eligibilityReason` 属性绑定，在 ScoreArea 旁显示状态标签。

## 9. 依赖注入（main.py）

```text
ApiClient
  → NetworkMonitor(api_client)
  → TextSourceGateway
    → TextIdFetcher(text_source_gateway)
      → TypingSessionContext(network_monitor, text_id_fetcher)
        → TypingAdapter(typing_service, score_gateway, session_context)
          → Bridge(typing_adapter, text_adapter, ...)
```

新增三步装配，插入在 `ScoreGateway` 之后、Adapter 之前。

## 10. 测试策略

### 单元测试（纯 Python，不需要 Qt）

| 测试 | 验证 |
|------|------|
| `test_network_session_confirmed` | 网络来源 + text_id 已知 → CONFIRMED |
| `test_local_session_pending_then_resolved` | 本地来源 + 延迟查询 → PENDING → CONFIRMED |
| `test_edited_text_ineligible` | 任何来源 + 编辑过 → INELIGIBLE |
| `test_slice_mode_na` | 分片 → NA，零查询 |
| `test_shuffle_mode_na` | 乱序 → NA，零查询 |
| `test_clipboard_mode_na` | 剪贴板 → NA，零查询 |
| `test_manual_mode_na` | 手动输入 → NA，零查询 |
| `test_offline_ineligible` | 离线 + text_id 未知 → INELIGIBLE |
| `test_offline_confirmed_still_works` | 离线 + text_id 已知 → CONFIRMED |
| `test_eligibility_reason_messages` | 每种状态返回正确的中文消息 |
| `test_phase_transitions` | IDLE→READY→TYPING→COMPLETED→IDLE |
| `test_text_id_lookup_cache` | 同一内容第二次查询命中缓存 |
| `test_mark_edited_after_setup` | setup 后 mark_text_edited → INELIGIBLE |

## 11. 迁移策略（渐进式）

1. **Phase 1**：引入 `TypingSessionContext`，旧逻辑暂保留
2. **Phase 2**：Bridge 载文方法同时更新状态机 + 旧状态
3. **Phase 3**：`_submit_score_async` 改为读状态机 `can_submit_score()`
4. **Phase 4**：验证所有场景后，移除 Bridge 中的旧载文状态字段

## 12. 改动范围

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/backend/application/session_context.py` | 新建 | 状态机 + NetworkMonitor + TextIdFetcher |
| `src/backend/presentation/adapters/typing_adapter.py` | 修改 | 注入 session_context, 新增信号, 修改两个方法 |
| `src/backend/presentation/bridge.py` | 修改 | 注入 session_context, 载文方法调用状态机, 新增信号 |
| `src/qml/typing/SliceConfigDialog.qml` | 修改 | 传递 isEdited 标志 |
| `src/qml/pages/TypingPage.qml` | 修改 | 绑定 uploadStatus / eligibilityReason |
| `main.py` | 修改 | 装配三步 |
| `tests/test_session_context.py` | 新建 | 单元测试 |
| `docs/ARCHITECTURE.md` | 修改 | 新增状态机章节 |
| `docs/reference/bridge-slots.md` | 修改 | 新增信号/属性文档 |

**不改动**：TypingService, TypingState, TextAdapter, TextSourceGateway, LoadTextUseCase, ScoreGateway, workers/
