# 统一低内存载文管线计划书
<!-- 状态: proposed | 最后验证: 2026-05-30 -->

## 背景

当前项目已经在 QML 层把多个载文入口尽量共享为 `TextLoadPanel`、`SliceSettingsPanel`、`SliceCriteriaPanel` 等组件，但 Python 层仍有两类载文模型并存：

- **文本型分片**：自定义载文、极速杯载文、内置本地文本会把完整文本传入 `Bridge.setupSliceMode(text, ...)`，由 `TypingSessionContext.setup_slice_mode()` 保存整篇 `_slice_text`，再按当前片取子串。见 `src/qml/pages/CustomLoadTextPage.qml:39-107`、`src/qml/pages/JisuBeiPage.qml:116-171`、`src/backend/presentation/bridge.py:1294-1358`、`src/backend/application/session_context.py:236-297`。
- **来源型分片**：本地文库、练单器按段加载，`TextLoadCoordinator` 在段落结果到达后调用 `setup_sourced_slice_mode()`，会话只缓存当前段。见 `src/backend/presentation/text_load_coordinator.py:164-246`。

这导致行为和性能不统一：

- 自定义/极速杯的历史进度 key 依赖全文内容 hash，必须先拿到完整文本才能判断是否有进度。见 `src/qml/pages/CustomLoadTextPage.qml:14-28`、`src/qml/pages/JisuBeiPage.qml:55-80`。
- 极速杯选择文本时会通过 `getTextContentById()` 获取完整 content，后端当前 `GET /api/v1/texts/{id}` 返回整篇详情。见 `src/qml/pages/JisuBeiPage.qml:33-52`、`src/backend/integration/leaderboard_fetcher.py:134-150`。
- 本地文库普通分片已经改为 `load_article_segment(article_id, start, length)` 按字符窗口读取，避免每次分片全量读入；但全文乱序仍需要完整文本。见 `src/backend/integration/file_local_article_repository.py:53-65`、`src/backend/integration/file_local_article_repository.py:127-176`。
- 练单器会将整个词库分组装入 session，全文乱序会 flatten 全部 entries 再 shuffle。见 `src/backend/domain/services/trainer_service.py:27-59`。
- 入口页依赖 `Qt.callLater()` 在导航后发起载文，时序是 UI 侧的隐式约定，不是后端可验证的载文事务。见 `src/qml/pages/CustomLoadTextPage.qml:88-108`、`src/qml/pages/LocalArticlesPage.qml:173-183`、`src/qml/pages/TrainerPage.qml:156-165`。

## 目标

1. 所有载文入口共用同一套"创建会话 → 获取当前段 → 导航 → 跟打 → 保存进度 → 下一段"的后端流程。
2. 默认分片路径对长文本保持低内存：只把当前跟打段传给 QML，不在 Bridge / SessionContext / QML TextArea 中保存整篇文本。
3. 历史进度不再依赖全文内容 hash；改用稳定的 `TextHandle` 标识源、版本、参数和乱序 seed。
4. 顺序分片、随机下一段、当前段乱序、全文乱序、恢复进度、达标次数、自动降指标都通过同一套状态机处理。
5. 取消基于 `Qt.callLater()` 的载文时序假设，改为显式 page-ready / pending-request 协议。

## 非目标

- 不把"百万字全文一次性显示在 UpperPane"伪装成低内存。QML TextArea/TextEdit 本身需要持有显示文本；超大文本必须默认走分片或分页。
- 不要求在没有服务端 range/segment API 的情况下让远程文本也做到严格低内存。客户端无法从只返回整篇 content 的 HTTP API 中按字符段取数据。
- 不在本计划中实现代码；本文件只定义设计、迁移顺序、验收标准。

## 决策

采用 **TextHandle + SegmentProvider + TextSessionUseCase** 的统一载文管线。

核心思想：所有载文来源本质上都是"一个字符序列"，区别仅在于字符序列存放在哪里（内存或文件）。切段、乱序、分片状态管理、指标、进度保存/恢复——这些全部是同一套逻辑，不应该按来源分支。唯一需要抽象为接口的是**数据获取**：给定字符范围，返回文本。

```text
QML 入口页
  -> Bridge.startTextSession(request)
  -> TextAdapter（Worker 线程）
  -> TextSessionUseCase.open(request)
    -> 构造 TextHandle
    -> 根据来源创建 SegmentProvider（InMemory 或 File）
    -> 初始化分片状态（统一逻辑，不区分来源）
    -> provider.get_segment(start, length) 取当前段
  -> Bridge.textLoaded(current_segment_text, -1/text_id, title)
  -> TypingPage.handleLoadedText(...)
```

其中：

- `TextHandle` 是"文本身份"，不是文本内容。
- `SegmentProvider` 是"给定字符范围返回文本"的能力（Port 协议），只有两种实现：InMemory（字符串已在内存中，字符串切片）和 File（从磁盘读取，小文件全量加载，大文件配合稀疏字符索引按需读取）。
- `TextSessionUseCase` 统一处理所有业务逻辑：分片状态、导航（下一段/上一段/随机段）、乱序（当前段/全文）、指标管理、进度保存/恢复。不区分来源，不分支。
- `TextSessionContext` 不再保存整篇 `_slice_text`，只保存当前段内容、段数、当前 index、metrics、进度和乱序 seed。
- `TextLoadCoordinator`（Presentation 层）保留为 Bridge 的内部协调器，继续管理来源切换状态、分片参数等 UI 协调职责，但取段操作委托给 TextSessionUseCase。

调用链遵循现有分层规则 `Bridge → Adapter → UseCase → Port`：TextAdapter 负责 Worker 线程调度和信号发射，TextSessionUseCase 负责业务编排，SegmentProvider 由 Integration 层实现。

## 目标数据模型

### TextHandle

建议新增 `src/backend/models/dto/text_session.py`：

```python
@dataclass(frozen=True)
class TextHandle:
    kind: Literal[
        "memory_text",
        "local_source",
        "local_article",
        "trainer",
        "remote_text",
        "clipboard",
    ]
    identifier: str
    title: str
    char_count: int
    version: str
    source_key: str = ""
    server_text_id: int | None = None
```

`version` 必须能识别内容变化：

| 来源 | identifier | version 建议 |
|:---|:---|:---|
| 自定义输入 | 临时 UUID 或 streaming hash | 内容 hash；因为用户已在内存中输入 |
| 剪贴板 | 临时 UUID 或 streaming hash | 内容 hash |
| 内置本地文本 | source key | 文件 size + mtime + 可选 manifest hash |
| 本地文库 | article id | 文件 size + mtime |
| 练单器 | trainer id | 文件 size + mtime + group size |
| 极速杯/远程文本 | server text id | server updatedAt / clientTextId / contentVersion |

### SegmentResult

```python
@dataclass(frozen=True)
class SegmentResult:
    content: str
    index: int
    total: int
```

不需要 `SegmentRequest`。provider 接口直接接收 `start` 和 `length` 参数。

## Provider 设计

核心认识：所有来源的差异只是"字符序列从哪读"。切段、乱序、状态管理、进度——全部由 TextSessionUseCase 统一处理，provider 只负责数据获取。

统一协议：

```python
class TextSegmentProvider(Protocol):
    def get_segment(self, start: int, length: int) -> str: ...
    def get_total_chars(self) -> int: ...
```

只有两种实现，对应两类数据访问方式：

| 数据来源 | 入口 | Provider |
|:---|:---|:---|
| 用户在 TextArea 输入 | 自定义载文 | InMemory |
| 粘贴板内容 | 剪贴板载文 | InMemory |
| HTTP API 拉取到内存 | 极速杯 | InMemory |
| 磁盘 `.txt` 文件 | 本地文库 | File |
| 磁盘词库文件（按行解析 entries，按 group 拼接） | 练单器 | File |
| bundled `.txt` 文件 | 内置本地文本 | File |

### InMemorySegmentProvider

用于字符串已在内存中的场景：自定义输入、剪贴板、小型已拉取远程文本。

- `get_segment`：字符串切片 `self._text[start:start+length]`，O(1)。
- `get_total_chars`：`len(self._text)`，O(1)。

阈值：超过 `memory_text_limit` 时建议导入为本地文库文件。

### FileSegmentProvider

用于字符序列在磁盘文件中的场景：内置本地文本、本地文库、练单器（词库文件，按 group 拼接段落）。

根据文件大小采用不同策略：

- **小文件**（低于阈值）：首次访问时全量读入内存，后续等同于 InMemory 的字符串切片。
- **大文件**（超过阈值）：不全量加载，通过稀疏字符索引定位 byte offset 后按需读取。

#### 稀疏字符索引

大文件的 `get_segment` 必须配合索引，否则每次读取都要从文件头扫描，第 K 段的时间复杂度为 `O(K * slice_size)`。

索引结构：有序数组，每 N 个字符记录一次 byte offset。

```json
[
  {"c": 0, "b": 0},
  {"c": 10000, "b": 29876},
  {"c": 20000, "b": 59432}
]
```

索引构建与缓存：

1. `FileSegmentProvider` 打开文件时检查索引缓存是否存在且有效（文件 size + mtime 匹配）。
2. 没有 → 扫描全文件建索引 → 写入缓存 → 加载到内存。
3. 有 → 直接加载到内存。
4. 后续所有 `get_segment` 用内存索引二分查找 + seek，O(log N)。

索引存储位置：`user_data_dir() / "indexes" / "{file_hash}.json"`（约 1-2KB / 百万字，可忽略）。

复杂度目标：

- 有索引：读取第 K 段约 `O(log N + slice_size)` 时间，`O(slice_size)` 内存。
- 索引首次构建：`O(file_size)` 时间，仅一次。

#### 练单器特殊处理

练单器的文件格式是词库（按行解析 entries，按 group 拼接）。FileSegmentProvider 需支持自定义解析逻辑：读取文件时按行拆分为 entries，`get_segment` 按字符范围从拼接后的字符串中截取。

### 远程文本

极速杯/服务端文本在服务端提供 segment API 之前，降级为：

- 小文本：整篇拉取后走 InMemorySegmentProvider。
- 大文本：提示"服务端不支持按段载文"，禁止低内存分片。

服务端提供 segment API 后，可新增一种远程 FileSegmentProvider 变体，通过 HTTP range 请求取段。

## 统一业务逻辑（TextSessionUseCase）

所有来源共享同一套逻辑，不分支：

### 分片初始化

```python
def open(self, request: TextSessionRequest) -> SegmentResult:
    provider = self._create_provider(request.handle)  # InMemory 或 File
    total_chars = provider.get_total_chars()
    total_slices = (total_chars + request.slice_size - 1) // request.slice_size
    # 初始化分片状态（统一，不区分来源）
    self._context.setup(total_slices, request.slice_size, request.criteria, ...)
    # 取第一段
    return self._get_segment(request.start_slice)
```

### 导航

```python
def next_segment(self) -> SegmentResult:
    self._context.advance_index()
    return self._get_segment(self._context.slice_index)

def prev_segment(self) -> SegmentResult:
    self._context.back_index()
    return self._get_segment(self._context.slice_index)

def random_segment(self) -> SegmentResult:
    self._context.pick_random_unvisited()
    return self._get_segment(self._context.slice_index)
```

### 乱序

当前段乱序和全文乱序都是 UseCase 的逻辑，不是 provider 的：

```python
def shuffle_current_segment(self) -> str:
    """对当前段内容做局部 shuffle。"""
    content = self._get_segment(self._context.slice_index).content
    return self._shuffle_text(content, seed)

def shuffle_all_virtual(self, seed: int) -> SegmentResult:
    """全文虚拟乱序：用 seed 生成 permutation，只 materialize 当前段。"""
    # 详见"全文乱序"章节
```

### 进度保存/恢复

统一 key 生成，统一保存格式：

```python
progress_key = sha256(handle.kind + ":" + handle.identifier + ":" + handle.version
                      + ":" + slice_size + ":" + shuffle_seed)
```

## 全文乱序

全文乱序是 UseCase 的逻辑，与 provider 无关。provider 只需提供 `get_segment(start, length)` 一个能力。

实现方案分级：

| 方案 | 内存 | 时间 | 适用 |
|:---|:---|:---|:---|
| 全量 shuffle | `O(N)` | `O(N)` 初始化 | 小文本（`<= memory_text_limit`） |
| 虚拟 permutation（Feistel / affine） | `O(1)` | `O(segment * retries)` | 大文本 |

小文本：调用 `provider.get_segment(0, total_chars)` 拿到完整字符串，Fisher-Yates shuffle，创建新的 InMemorySegmentProvider，后续按普通分片取段。

大文本：不 materialize 完整 shuffled text。用 seed + virtual permutation 计算每个虚拟位置对应的原文字符 index，调用 `provider.get_segment(original_index, 1)` 逐字符取当前段。需要 provider 支持高效的单字符随机访问（FileSegmentProvider 配合稀疏字符索引）。

注意：真正随机访问"单个字符"对 UTF-8/GB18030 文件并不天然便宜，因此大文件全文乱序依赖稀疏字符索引。若 provider 不支持高效随机访问，则禁用全文乱序或提示需要建立索引。

## 进度恢复机制

进度存储 key 改为：

```text
progress_key = sha256(handle.kind + ":" + handle.identifier + ":" + handle.version + ":" + slice_size + ":" + shuffle_seed)
```

保存内容继续保留：

- `current_slice`
- `total_slices`
- `slice_size`
- `slice_pass_counts`
- `slice_stats`
- `metrics`
- `slice_metrics`
- `advance_mode`
- `shuffle_seed`

但不再保存 `text_preview` 为进度匹配依据；标题仅用于展示和旧格式回退。

迁移策略：

1. 新 key 查找失败时，保留现有 title scan 兼容旧数据。
2. 首次保存新 key 后，清理同标题旧 key。
3. 对 `custom_text` 旧路径保留内容 hash，直到 QML 不再传全文。

## QML 入口统一

四个入口页不再分别调用：

- `setupSliceMode(text, ...)`
- `loadLocalArticleSegment(...)`
- `loadTrainerSegment(...)`
- `loadFullText(text, ...)`

而是组装统一 request，经 Bridge → TextAdapter → TextSessionUseCase 标准链路：

```js
appBridge.startTextSession({
  kind: "remote_text",
  identifier: selectedText.id,
  title: textTitle(selectedText),
  sliceMode: true,
  sliceSize: sliceSettingsPanel.sliceSize,
  startSlice: sliceSettingsPanel.startSlice,
  fullShuffle: sliceSettingsPanel.fullShuffleChecked,
  criteria: sliceCriteriaPanel.toRequest(),
  restoredProgress: restoredProgress || ""
})
```

Bridge 的 `startTextSession` slot 转发给 TextAdapter，TextAdapter 在 Worker 中调用 TextSessionUseCase.open()，由 UseCase 根据 handle 创建对应的 provider 取段。

`TextLoadPanel` 不应为了判断进度而把本地或远程完整文本加载进 TextArea。它应显示 metadata 和预览；只有"编辑自定义文本"场景才使用 TextArea 保存正文。

## 导航时序

替换 `Qt.callLater()`：

```text
EntryPage
  -> appBridge.queueTextSession(request)
  -> navigationView.push(TypingPage)
TypingPage.onActiveChanged(active=true)
  -> appBridge.activateQueuedTextSession()
Bridge
  -> emit textLoaded(current segment)
```

这样载文动作由后端 pending request 驱动，QML 页面只声明"我已 ready"，不再依赖事件循环延迟。

## 实施步骤

### 阶段 0：锁现有行为

新增回归测试：

- 自定义载文、极速杯、本地文库、练单器都能保存和恢复 `current_slice`。
- 上一段/下一段/随机段后保存的进度等于实际载入段。
- 全文乱序恢复 seed 后段内容稳定。
- 超大本地文本普通分片不调用全文读取。

### 阶段 1：引入模型和 provider 协议

新增：

- `models/dto/text_session.py`（TextHandle、SegmentResult）
- `ports/text_segment_provider.py`（TextSegmentProvider 协议：`get_segment`、`get_total_chars`）
- `integration/in_memory_segment_provider.py`（InMemorySegmentProvider 实现）
- `application/usecases/text_session_usecase.py`（统一业务逻辑：分片初始化、导航、乱序、进度）

在 TextAdapter 中新增 `startTextSession()` 方法，经 Worker 调用 TextSessionUseCase。

先保留旧 Bridge slots 作为兼容层，新增 `startTextSession()` 并让自定义文本走新路径（InMemorySegmentProvider）。

### 阶段 2：统一所有文件型来源

新增 `integration/file_segment_provider.py`（FileSegmentProvider 实现），复用 `FileLocalArticleRepository` 的流式读取。小文件全量读入内存，大文件配合稀疏字符索引按需读取。索引缓存存于 `user_data_dir() / "indexes"`。本地文库、内置本地文本、练单器统一走 FileSegmentProvider。

### 阶段 3：虚拟全文乱序

在 TextSessionUseCase 中实现全文虚拟乱序逻辑。小文本全量 shuffle，大文本用 Feistel permutation。先支持 InMemory + File provider；远程待 segment API 可用后支持。

### 阶段 4：服务端 range API

服务端和客户端同时支持 `metadata` 与 `segments`。在 API 不可用时保留小文本整篇拉取降级，大文本提示不可低内存载入。

### 阶段 5：删除旧路径

删除或废弃：

- `setupSliceMode(text, ...)` 对外 QML 调用。
- `loadLocalArticleSegment()` / `loadTrainerSegment()` 作为入口页直接调用。
- `getLocalTextContent()` 在载文入口中的全文预加载用途。
- 基于完整正文的远程进度检查。
- `SessionContext.setup_slice_mode()` 和 `setup_sourced_slice_mode()` 的区分，统一由 TextSessionUseCase 管理。
- TextLoadCoordinator 中来源特定的状态字段（`_source_slice_backend`、`_source_slice_article_id` 等），统一由 TextHandle + TextSessionUseCase 管理。

## 验收标准

1. 本地百万字 `.txt`：载入第 5000 段时，Bridge/QML 只收到当前段文本；内存峰值不随全文长度线性增长。
2. 极速杯在服务端 segment API 可用时：进入分片模式不拉完整 content。
3. 自定义文本超过阈值时：UI 提示转为本地文库文件或分片导入，不允许静默塞入 TextArea。
4. 四个入口页使用同一个 `startTextSession(request)`。
5. 顺序/随机/上一段/下一段/重打/当前段乱序/全文虚拟乱序都通过同一套代码处理，不按来源分支。
6. 历史进度恢复不依赖全文 hash；同一文本内容变更后不会误用旧进度。
7. 无 `Qt.callLater()` 作为载文正确性的必要条件。

## 风险与规避

| 风险 | 规避 |
|:---|:---|
| 远程服务不支持按段 API | 小文本降级整篇，大文本禁用低内存载文并提示 |
| GB18030 / UTF-8 字符 offset 难以随机访问 | 本地文件建立稀疏字符索引，不直接用 byte offset 当 char offset |
| 全文乱序语义要求全局 permutation | 小文本全量 shuffle，大文本用 seed + virtual permutation 只 materialize 当前段 |
| 旧进度丢失 | 新 key 查找失败时按 title 回退，保存新进度后清理旧项 |
| QML TextArea 仍可能装入全文 | 入口页只为自定义编辑保留 TextArea；库文本只展示 metadata/预览 |
| 迁移面过大 | 分阶段迁移，旧 slots 暂时保留为兼容层 |

## 需要的服务端协作

严格低内存远程载文依赖服务端提供：

- 文本 metadata（字数、版本、clientTextId）。
- 按字符 offset 的 segment API。

如果服务端暂不改，客户端只能做到本地文件/练单器/自定义小文本的低内存统一；远程大文本无法"完美"规避整篇下载。

## 计划结论

最合适的方案不是继续修补 `setupSliceMode(text)`，而是把"文本内容"从载文入口参数中移走，改为传 `TextHandle`。所有入口都只创建会话请求；真正取段由 provider 负责。所有来源共享同一套业务逻辑（切段、乱序、导航、进度），不按来源分支。唯一需要抽象的是数据获取——字符序列在内存还是文件。这样可以同时解决：

- 多入口 Python 逻辑不统一；
- 本地长文全量读入；
- 进度恢复依赖全文；
- 全文乱序高内存；
- QML 导航时序靠 `Qt.callLater()`。
