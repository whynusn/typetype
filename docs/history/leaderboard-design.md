# 文本排行榜设计文档

> 最后更新：2026-04-14
> 状态：待审阅

## 一句话

将排行榜从"按时间维度（日/周/总榜）"改为"按文本维度"，每个文本独立排行，
提供浏览页（Master-Detail）+ 跟打页即时查看（右侧面板）两种入口。

---

## 现状分析

### 当前排行榜实现

- 侧边栏有三个入口：日榜、周榜、总榜（后两个是 stub）
- DailyLeaderboard 页面固定查询 `jisubei` 来源的最新文本排行榜
- 数据链路：`loadLeaderboard(source_key)` → 获取最新文本 → 按 textId 查排行榜
- 服务端已有 `GET /api/v1/texts/{textId}/leaderboard`（按 textId 查排行榜）

### 问题

1. 排行榜只关联"最新一篇"文本，历史文本没有排行入口
2. 每个来源的每篇文本都有独立排行，无法用"日/周/总"时间维度统一
3. 侧边栏三个入口浪费空间，且周榜/总榜无法实现（没有时间维度聚合逻辑）

### 服务端现状

| 端点 | 状态 | 说明 |
|------|------|------|
| `GET /api/v1/texts/catalog` | ✅ 已有 | 返回所有 active 来源 |
| `GET /api/v1/texts/latest/{sourceKey}` | ✅ 已有 | 获取来源最新文本 |
| `GET /api/v1/texts/{textId}/leaderboard` | ✅ 已有 | 按 textId 查排行榜 |
| `GET /api/v1/texts/{textId}/best` | ✅ 已有 | 当前用户最佳成绩 |
| `GET /api/v1/texts/by-source/{sourceKey}` | ❌ 需新增 | 列出来源下所有文本 |

---

## 设计方案

### 整体架构

```
侧边栏变更：
  删除：日榜、周榜、总榜（3个入口）
  新增：文本排行（1个入口）

新增页面：
  TextLeaderboardPage — Master-Detail 布局

修改页面：
  TypingPage — 右侧叠加排行榜面板
```

### 1. 新增服务端 API

`GET /api/v1/texts/by-source/{sourceKey}`

```json
// Response 200
{
  "code": 200,
  "data": [
    {
      "id": 42,
      "title": "春江花月夜",
      "charCount": 200,
      "createdAt": "2026-04-10T12:00:00"
    },
    {
      "id": 43,
      "title": "岳阳楼记",
      "charCount": 368,
      "createdAt": "2026-04-09T10:00:00"
    }
  ]
}
```

- 返回该来源下所有文本的摘要（不含 content，只含 id/title/charCount/createdAt）
- 按 created_at DESC 排序
- TextMapper 已有 `findBySourceId(sourceId)`，只需加 Mapper 方法返回摘要字段

### 2. 客户端数据层变更

#### 新增 TextCatalogGateway（或扩展现有 Gateway）

```
方法：
  get_texts_by_source(source_key: str) -> list[TextSummaryItem]
  # 调用 GET /api/v1/texts/by-source/{sourceKey}
  
  get_text_leaderboard(text_id: int) -> LeaderboardResult
  # 调用 GET /api/v1/texts/{textId}/leaderboard（已有）
```

#### 新增/修改 Worker

- `TextListWorker`：异步加载某来源下的文本列表
- 现有 `LeaderboardWorker` 复用，但改为按 text_id 加载

#### Bridge 新增信号/Slot

```python
# 新增
textListLoaded(list)       # 文本列表加载完成
textListLoadFailed(str)    # 加载失败
textListLoading: bool      # 加载中

@Slot(str)
def loadTextList(source_key: str)  # 触发加载文本列表

# 排行榜改为支持按 textId 直接加载
@Slot(int)
def loadLeaderboardByTextId(text_id: int)  # 新增
```

### 3. 文本排行页（TextLeaderboardPage）

#### 布局

```
┌─────────────────────────────────────────────────────┐
│  🏆 文本排行榜    [极速杯▾]  刷新                      │
├────────────────────┬────────────────────────────────┤
│  📝 文本列表 (12)   │  春江花月夜 的排行榜 (42人)       │
│                    │                                │
│ ▸ 春江花月夜  ⭐#6  │  名次  用户        速度   准确率   │
│   200字 · 42人     │  🥇   打字狂人    156.3  98.7%   │
│                    │  🥈   SpeedDemon  148.7  97.2%   │
│   岳阳楼记  #12    │  🥉   键盘侠客    142.1  99.1%   │
│   368字 · 38人     │  4    TypingMaster 138.5 96.8%   │
│                    │  ...                             │
│   出师表   —       │  6    我(Kurisu)  128.9  94.2%   │
│   641字 · 29人     │  ...                             │
│                    │                                  │
│   滕王阁序  #3     │                                  │
│   773字 · 25人     │                                  │
└────────────────────┴────────────────────────────────┘
```

#### 组件选择

| 区域 | 组件 | 说明 |
|------|------|------|
| 来源选择 | RinUI `ComboBox` | 下拉切换来源，触发 `loadTextList(source_key)` |
| 文本列表 | RinUI `ListView` + 自定义 delegate | 左侧 280px，每个 item 展示标题/字数/排名 |
| 排行榜表 | 复用 DailyLeaderboard 的 table 结构 | 右侧填充，`ListView` + header row |
| 加载状态 | RinUI `BusyIndicator` | 列表和排行榜各自独立 loading |
| 错误处理 | 文本提示（非 InfoBar） | 静默降级，不弹窗 |

#### 数据流

```
页面加载
  → loadCatalog() 获取来源列表 → 填充 ComboBox
  → 默认选中第一个来源 → loadTextList(source_key)
  → 文本列表加载完成 → 默认选中第一项 → loadLeaderboardByTextId(text_id)
  → 排行榜加载完成 → 渲染右侧面板

用户切换来源
  → ComboBox.onActivated → loadTextList(new_source_key)
  → 清空右侧排行榜 → 文本列表加载完成 → 自动选中第一项 → 加载排行榜

用户点击文本
  → loadLeaderboardByTextId(text_id)
  → 排行榜加载完成 → 更新右侧面板
```

### 4. TypingPage 右侧面板

#### 布局

```
┌───────────────────────────────┬──────────┐
│ 工具栏 [载文] [📋] [🔄] [🏆]  │          │
├───────────────────────────────┤  🏆      │
│ 春江潮水连海平，海上明月共潮生  │  春江花月夜 │
├───────────────────────────────┤          │
│ 速度 128.9  击键 6.8  准确率…  │ 我的排名   │
├───────────────────────────────┤  #6/42   │
│ [输入区域]                     │          │
├───────────────────────────────┤ 🥇 打字狂人│
│ 历史记录                       │ 🥈 Speed… │
│                               │ 🥉 键盘侠… │
│                               │ ...      │
│                               │ 6 我     │
│                               │ ...      │
└───────────────────────────────┴──────────┘
```

#### 交互规则

```
[textId === 0]
  面板显示"本地文本不参与排行"，灰色提示，不发起网络请求

[textId > 0，载文完成]
  面板自动加载排行榜（异步），显示 BusyIndicator

[加载成功]
  展示"我的排名"高亮卡片 + Top 10 列表

[加载失败 / 无网络]
  静默显示"暂无排行数据"，不弹 InfoBar，不阻塞打字

[打字结束，成绩提交成功]
  自动刷新排行榜（重新请求）

[面板切换]
  工具栏 🏆 按钮 toggle 面板显示/隐藏
  面板宽度固定 280px，不挤压打字区域
```

#### 关键保证

1. 排行榜面板是纯信息展示，绝不阻塞打字主流程
2. 所有网络请求异步，失败静默降级
3. textId=0 时不发请求，直接显示静态提示
4. 面板默认隐藏，用户按需展开（节省屏幕空间）

---

## 侧边栏变更

### 删除

- `pages/DailyLeaderboard.qml`（可保留文件，从导航中移除）
- `pages/WeeklyLeaderboard.qml`（stub）
- `pages/AllTimeLeaderboard.qml`（stub）

### 新增

- `pages/TextLeaderboardPage.qml`

### Main.qml 变更

```qml
// 删除
NavigationSubItem { title: qsTr("日榜"); ... }
NavigationSubItem { title: qsTr("周榜"); ... }
NavigationSubItem { title: qsTr("总榜"); ... }

// 新增（扁平化，不再用 NavigationSubItem）
NavigationItem {
    title: qsTr("文本排行")
    icon: "ic_fluent_trophy_20_regular"
    page: Qt.resolvedUrl("pages/TextLeaderboardPage.qml")
}
```

---

## 数据模型

### TextSummaryItem（DTO）

```python
@dataclass
class TextSummaryItem:
    id: int
    title: str
    char_count: int
    created_at: str  # ISO datetime
    player_count: int = 0  # 打过此文本的人数（可选，后续增强）
```

### LeaderboardEntry（已有，无需修改）

```python
@dataclass
class LeaderboardEntry:
    rank: int
    nickname: str
    speed: float
    key_stroke: float
    code_length: float
    accuracy_rate: float
    wrong_char_count: int
    duration: float
    created_at: str
```

---

## 实施步骤

### Phase 1：服务端 — 新增文本列表 API

1. TextMapper 添加 `findBySourceIdSummary(Long sourceId)` 方法（只查 id/title/charCount/createdAt）
2. TextService 添加 `getTextSummariesBySourceKey(String sourceKey)` 方法
3. TextController 添加 `GET /api/v1/texts/by-source/{sourceKey}` 端点
4. 测试

### Phase 2：客户端数据层

1. 新增 `TextListWorker`（异步加载文本列表）
2. LeaderboardAdapter 添加 `loadTextList(source_key)` 方法 + `textListLoaded/textListLoadFailed` 信号
3. LeaderboardAdapter 添加 `loadLeaderboardByTextId(text_id)` 方法
4. Bridge 添加对应信号/Slot
5. 测试

### Phase 3：文本排行页

1. 新建 `TextLeaderboardPage.qml` — Master-Detail 布局
2. 左侧：ComboBox 来源选择 + ListView 文本列表
3. 右侧：排行榜表（复用 DailyLeaderboard 的表格结构）
4. 更新 `Main.qml` 导航项

### Phase 4：TypingPage 排行榜面板

1. 新建 `typing/LeaderboardPanel.qml` — 右侧 280px 面板
2. TypingPage 添加面板 + 🏆 toggle 按钮
3. 处理 textId=0 / loading / loaded / failed 四种状态
4. 打字结束时自动刷新

### Phase 5：清理

1. 从 Main.qml 导航中移除日榜/周榜/总榜
2. DailyLeaderboard.qml 可保留（作为代码参考）或删除

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 来源下文本太多（数百篇），列表加载慢 | API 只返回摘要（无 content），数据量极小；后续可加分页 |
| 排行榜面板遮挡打字区域 | 面板默认隐藏，用户按需展开；宽度固定 280px |
| 无网络时面板体验差 | textId=0 直接跳过；网络失败静默降级 |
| ComboBox 切换来源时竞态 | 切换时清空旧数据，用 loading 状态守卫 |

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-14 | 初始设计：文本排行榜 Master-Detail + TypingPage 面板 |
