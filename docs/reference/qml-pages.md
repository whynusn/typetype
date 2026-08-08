# QML 页面与组件速查
<!-- 状态: active | 最后验证: 2026-07-27 -->

> 所有 QML 文件位于 `src/qml/` 下。

## 页面清单（导航入口）

| 文件 | 导航标题 | 依赖信号 |
|------|---------|---------|
| `pages/TypingPage.qml` | 跟打 | `textLoaded`, `textLoadFailed`, `wenlaiLoadFailed`, `uploadResult`, `loggedinChanged` |
| `pages/WeakCharsPage.qml` | 薄弱字 | `weakestCharsLoaded` |
| `pages/TextLeaderboardPage.qml` | 文本排行 | `catalogLoaded`, `textListLoaded`, `leaderboardLoaded`, `leaderboardLoadFailed` |
| `pages/UploadTextPage.qml` | 上传文本 | `uploadResult`, `loggedinChanged` |
| `pages/ProfilePage.qml` | 个人中心 | `loginResult`, `registerResult`, `loggedinChanged`, `userInfoChanged`, `loginStateInitialized` |
| `pages/SettingsPage.qml` | 设置 | `wenlaiLoginResult`, `wenlaiConfigChanged`, `wenlaiDifficultiesLoaded`, `wenlaiCategoriesLoaded` |
| `pages/TextLoadHubPage.qml` | 载文 | `registryFederatedEntriesLoaded`, `registryFederatedEntriesLoadFailed`, `reposChanged`（统一载文中心，顶部 Segmented 切换本地/源仓库/练单器/自定义/极速杯） |
| `pages/RepoEntriesPage.qml` | 条目列表 | `entryClicked`（联邦聚合目录条目浏览） |

> 已移除：`DailyLeaderboard.qml`、`WeeklyLeaderboard.qml`、`AllTimeLeaderboard.qml`、`JisuBeiPage.qml`、`LocalArticlesPage.qml`、`TextLibraryPage.qml`、`CustomLoadTextPage.qml`、`TrainerPage.qml`（功能合并入 `TextLoadHubPage.qml`）

## TypingPage 子组件

| 文件 | 职责 |
|------|------|
| `typing/ToolLine.qml` | 工具栏（载文/剪贴板/晴发文/重打/排行榜按钮） |
| `typing/UpperPane.qml` | 文本显示区域 |
| `typing/ScoreArea.qml` | 实时速度/击键/码长/错误数展示 |
| `typing/LowerPane.qml` | 输入区域（含 `suppressTextChanged` 防程序化触发统计） |
| `typing/HistoryArea.qml` | 历史记录展示 |
| `typing/EndDialog.qml` | 打字结束成绩弹窗 |
| `typing/LeaderboardPanel.qml` | 右侧面板（toggle 显示），依赖 `textIdChanged` |
| `typing/SliceConfigDialog.qml` | 载文设置对话框（来源/文本选择/分片/全文载入） |

## 其他组件

| 文件 | 职责 |
|------|------|
| `components/AppText.qml` | 通用文本组件 |
| `components/ReposManagementPanel.qml` | 源仓库订阅管理面板（添加/删除/启停/刷新订阅，显示 manifest 摘要与信任徽章） |

## QML → Bridge 调用速查

| QML 页面 | 调用的 Bridge 方法 |
|----------|-------------------|
| TypingPage | `requestLoadText(key)`, `loadTextFromClipboard()`, `loadRandomWenlaiText()`, `loadNextWenlaiSegment()`, `loadPrevWenlaiSegment()`, `loadNextWenlaiSegmentWithScore()`, `setTextId(id)`, `setTextTitle(t)`, `handleLoadedText(doc, text)`, `handleStartStatus(s)`, `getScoreMessage()`, `setTextId(0)` |
| TypingPage (载文模式) | `collectSliceResult()`, `isLastSlice()`, `buildAggregateScore()`, `exitSliceMode()`, `shouldRetype()`, `handleSliceRetype()`, `loadNextSlice()` |
| SliceConfigDialog | `loadCatalog()`, `loadTextList(key)`, `getTextContentById(id)`, `loadFullText(text, srcKey)`, `setupSliceMode(text, size, ...)` |
| WeakCharsPage | `loadWeakChars()` |
| TextLeaderboardPage | `loadCatalog()`, `loadTextList(key)`, `loadLeaderboardByTextId(id)`, `loadLeaderboard(key)` |
| DailyLeaderboard | `loadLeaderboard("jisubei")`, `copyToClipboard(text)` |
| UploadTextPage | `uploadText(title, content, sourceKey, toLocal, toCloud)` |
| ProfilePage | `login(u, p)`, `register(u, p, n)`, `logout()`, `checkTokenStatus()` |
| SettingsPage | `loginWenlai(u, p)`, `logoutWenlai()`, `refreshWenlaiDifficulties()`, `refreshWenlaiCategories()`, `updateWenlaiConfig(...)`, `setBaseUrl(url)` |
| LeaderboardPanel | `loadLeaderboardByTextId(id)`, `copyToClipboard(text)` |
