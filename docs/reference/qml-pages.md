# QML 页面与组件速查
<!-- 状态: active | 最后验证: 2026-08-13 -->

> 所有 QML 文件位于 `src/qml/` 下。
> typetype-server 已移除（ADR-013）：登录、服务端排行榜、云端上传等槽/页面已删除；`ProfilePage` 与 `UploadTextPage` 保留为本地打字历史统计 / 本地文本保存页面。

## 页面清单（导航入口）

| 文件 | 导航标题 | 依赖信号 |
|------|---------|---------|
| `pages/TypingPage.qml` | 跟打 | `textLoaded`, `textLoadFailed`, `wenlaiLoadFailed`, `uploadResult` |
| `pages/WeakCharsPage.qml` | 薄弱字 | `weakestCharsLoaded` |
| `pages/ProfilePage.qml` | 个人中心 | `typingHistoryChanged`, `typingHistorySummaryChanged`（本地打字历史/统计；登录已移除） |
| `pages/SettingsPage.qml` | 设置 | `wenlaiLoginResult`, `wenlaiConfigChanged`, `wenlaiDifficultiesLoaded`, `wenlaiCategoriesLoaded`, `updateCheckFinished`, `updateDownloadProgress`, `updateStatusChanged` |
| `pages/TextLoadHubPage.qml` | 载文 | `registryFederatedEntriesLoaded`, `registryFederatedEntriesLoadFailed`, `registryFederatedEntriesLoadingChanged`, `textContentLoaded`（统一载文中心，顶部 Segmented 切换本地文库/开源文库/练单器/晴发文/AI 推荐/自定义；开源文库 tab 直接浏览联邦条目，晴发文/AI 为即时拉取入口） |
| `pages/ReposManagementPage.qml` | 管理源仓库 | `reposChanged`, `reposLoadFailed`（OTT Repo 订阅管理独立页面，浏览文本返回载文中心开源文库 tab） |

> 已移除：`TextLeaderboardPage.qml`、`DailyLeaderboard.qml`、`WeeklyLeaderboard.qml`、`AllTimeLeaderboard.qml`、`JisuBeiPage.qml`、`LocalArticlesPage.qml`、`TextLibraryPage.qml`、`CustomLoadTextPage.qml`、`TrainerPage.qml`、`RepoEntriesPage.qml`（本地功能合并入 `TextLoadHubPage.qml`，联邦条目浏览并入开源文库 tab；服务端排行榜/登录随 typetype-server 移除）

## TypingPage 子组件

| 文件 | 职责 |
|------|------|
| `typing/ToolLine.qml` | 工具栏（载文/剪贴板/晴发文/重打） |
| `typing/UpperPane.qml` | 文本显示区域 |
| `typing/ScoreArea.qml` | 实时速度/击键/码长/错误数展示 |
| `typing/LowerPane.qml` | 输入区域（含 `suppressTextChanged` 防程序化触发统计） |
| `typing/HistoryArea.qml` | 历史记录展示 |
| `typing/EndDialog.qml` | 打字结束成绩弹窗 |
| `typing/SliceConfigDialog.qml` | 载文设置对话框（来源/文本选择/分片/全文载入） |

## 其他组件

| 文件 | 职责 |
|------|------|
| `components/AppText.qml` | 通用文本组件 |
| `components/ReposManagementPanel.qml` | 源仓库订阅管理面板（添加/删除/启停/刷新订阅，显示 manifest 摘要与信任徽章；承载于 `ReposManagementPage`） |
| `components/RepoEntriesPanel.qml` | 开源文库条目列表面板（联邦条目富卡片/来源筛选/搜索/错误重试，`entryClicked`/`refreshRequested`/`manageRequested` 信号） |
| `components/WenlaiSourcePanel.qml` | 晴发文即时源面板（登录状态/配置摘要/「随机一篇」，`loadRequested` 信号） |
| `components/AiSourcePanel.qml` | AI 推荐即时源面板（API Key 引导/模型配置摘要/「生成一篇」，`loadRequested` 信号） |

## QML → Bridge 调用速查

| QML 页面 | 调用的 Bridge 方法 |
|----------|-------------------|
| TypingPage | `requestLoadText(key)`, `loadTextFromClipboard()`, `loadRandomWenlaiText()`, `loadNextWenlaiSegment()`, `loadPrevWenlaiSegment()`, `loadNextWenlaiSegmentWithScore()`, `setTextId(id)`, `setTextTitle(t)`, `handleLoadedText(doc, text)`, `handleStartStatus(s)`, `getScoreMessage()`, `setTextId(0)` |
| TypingPage (载文模式) | `collectSliceResult()`, `isLastSlice()`, `buildAggregateScore()`, `exitSliceMode()`, `shouldRetype()`, `handleSliceRetype()`, `loadNextSlice()` |
| SliceConfigDialog | `getLocalTextContent(key)`, `loadFullText(text, srcKey)`, `setupSliceMode(text, size, ...)` |
| WeakCharsPage | `loadWeakChars()` |
| ProfilePage | `loadTypingHistory()`, `setTrendRange(range)` |
| TextLoadHubPage | `loadFederatedEntries()`, `loadFederatedEntrySegment(...)`, `loadFederatedInlineEntry(...)`, `loadLocalArticles()`, `loadTrainers()`, `loadRandomWenlaiText()`, `requestAiText()`, `loadTextFromClipboard()` |
| ReposManagementPage | `getRepos()`, `addRepo(url)`, `removeRepo(url)`, `setRepoEnabled(url, enabled)`, `refreshRepos()`, `refreshRepo(url)`, `confirmRepoTrust(url)`, `rejectRepoTrust(url)` |
| UploadTextPage | `uploadText(title, content, sourceKey, toLocal, toCloud)`（云端上传已移除，仅本地保存） |
| SettingsPage | `loginWenlai(u, p)`, `logoutWenlai()`, `refreshWenlaiDifficulties()`, `refreshWenlaiCategories()`, `updateWenlaiConfig(...)`, `checkForUpdate()`, `downloadAndInstallUpdate(version)`, `dismissUpdate()`, `setScriptsEnabled(enabled)`, `updateAiBaseUrl(...)` |
