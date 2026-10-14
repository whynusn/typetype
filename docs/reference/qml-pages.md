# QML 页面与组件速查
<!-- 状态: active | 最后验证: 2026-08-19 -->

> 所有 QML 文件位于 `src/qml/` 下。
> typetype-server 已移除（ADR-013）：登录、服务端排行榜、云端上传等槽/页面已删除；`ProfilePage` 与 `UploadTextPage` 保留为本地打字历史统计 / 本地文本导入页面。

## 页面清单（导航入口）

| 文件 | 导航标题 | 依赖信号 |
|------|---------|---------|
| `pages/TypingPage.qml` | 跟打 | `textLoaded`, `textLoadFailed`, `wenlaiLoadFailed`, `aiTextPartial`, `aiTextFailed` |
| `pages/WeakCharsPage.qml` | 薄弱字 | `weakestCharsLoaded` |
| `pages/ProfilePage.qml` | 个人中心 | `typingHistoryChanged`, `typingHistorySummaryChanged`（本地打字历史/统计；登录已移除） |
| `pages/SettingsPage.qml` | 设置 | `updateCheckFinished`, `updateDownloadProgress`, `updateStatusChanged`, `zitiSchemesLoaded`（晴发文/AI/键盘信号由 `settings/` 子组件消费） |
| `pages/TextLoadHubPage.qml` | 载文 | `registryFederatedEntriesLoaded`, `registryFederatedEntriesLoadFailed`, `registryFederatedEntriesLoadingChanged`, `federatedSourceStatusChanged`, `textLoaded`, `textLoadFailed`（统一载文中心，顶部 Segmented 切换本地文库/开源文库/练单器/晴发文/AI 推荐/自定义；开源文库 tab 直接浏览联邦条目，晴发文/AI 为即时拉取入口；导入文本从本地文库 tab 头部「+」push `UploadTextPage.qml`） |

> 已移除：`ReposManagementPage.qml`、`TextLeaderboardPage.qml`、`DailyLeaderboard.qml`、`WeeklyLeaderboard.qml`、`AllTimeLeaderboard.qml`、`JisuBeiPage.qml`、`LocalArticlesPage.qml`、`TextLibraryPage.qml`、`CustomLoadTextPage.qml`、`TrainerPage.qml`、`RepoEntriesPage.qml`（订阅管理收敛到组头弹窗 `RepoConfigDialog`；联邦条目浏览并入开源文库 tab；服务端排行榜/登录随 typetype-server 移除）

## TypingPage 子组件

| 文件 | 职责 |
|------|------|
| `typing/ToolLine.qml` | 工具栏（晴发文/重打/发文/剪贴板/AI 推荐） |
| `typing/UpperPane.qml` | 文本显示区域（`setCursorAndScroll` 先重置光标再赋文本） |
| `typing/ScoreArea.qml` | 实时速度/击键/码长/错误数展示 |
| `typing/LowerPane.qml` | 输入区域（中间编辑拒绝提交；AI 流式期间锁定输入） |
| `typing/HistoryArea.qml` | 历史记录展示（右键复制成绩） |
| `typing/SliceSettingsPanel.qml` | 分片参数设置（载文中心与打字页共用） |
| `typing/SliceCriteriaPanel.qml` | 达标条件设置 |
| `typing/SliceProgressRestoreDialog.qml` | 分片进度恢复弹窗 |
| `typing/TextLoadPanel.qml` | 自定义 tab 纯文本输入面板（已收敛，仅剩输入+乱序） |

> 已移除：`EndDialog.qml`（打字结束成绩弹窗，从未 open 的死代码）、`SliceHelpers.qml`（死 singleton，逻辑已内联进 hub）。

## 其他组件

| 文件 | 职责 |
|------|------|
| `components/RepoEntriesPanel.qml` | 开源文库条目列表面板（组头卡片 + 手风琴 + 源级刷新/详情/管理 + 搜索去抖 + 错误重试；`entryClicked`/`refreshSourceRequested`/`sourceInfoRequested`/`manageRepoRequested` 信号） |
| `components/RepoConfigDialog.qml` | 订阅源管理弹窗（启用/信任/删除；`_syncingSwitch` 守卫防回写白调） |
| `components/SourceInfoDialog.qml` | 源详情弹窗（tier/健康状态/刷新频率覆盖；`sourceStatusChanged` 实时回流） |
| `components/InstantSourcePanel.qml` | 即时源面板骨架（图标/标题/描述/内容插槽/errorText/主操作行；晴发文与 AI 共用） |
| `components/WenlaiSourcePanel.qml` | 晴发文即时源面板（薄壳：登录状态行 + 配置摘要卡） |
| `components/AiSourcePanel.qml` | AI 推荐即时源面板（薄壳：未配置引导 + 配置摘要卡） |
| `components/EmptyState.qml` | 空态占位（居中 + 次级色；布局参数留在调用方） |
| `components/SettingSectionHeader.qml` | 设置页区块标题 |
| `helpers/TextSourceBehaviors.js` | 来源能力注册表 + 数据分派（`.pragma library`） |
| `helpers/SourceBadges.js` | trust/tier 徽章文案与配色单一事实源（配色经参数传 Theme 颜色） |
| `settings/` | SettingsPage 拆分区块：`WenlaiSection`/`AiSection`/`KeyboardDevicesSection`/`FontManagerDialog`（各自包含模型/对话框/Connections，主页只编排） |

> 已移除：`AppText.qml`（零引用死组件，统一走 RinUI typography 体系）、`ReposManagementPanel.qml`（订阅管理收敛到 `RepoConfigDialog`）。

## QML → Bridge 调用速查

| QML 页面 | 调用的 Bridge 方法 |
|----------|-------------------|
| TypingPage | `loadTextFromClipboard()`, `loadRandomWenlaiText()`, `loadNextWenlaiSegment()`, `loadPrevWenlaiSegment()`, `setTextId(id)`, `setTextTitle(t)`, `handleLoadedText(doc, text)`, `handleStartStatus(s)`, `getScoreMessage()`, `handleTextLoadFailed()`, `handleLoadFailed()`（失败复位 readOnly） |
| TypingPage (分片) | `collectSliceResult()`, `isLastSlice()`, `buildAggregateScore()`, `exitSliceMode()`, `shouldRetype()`, `handleSliceRetype()`, `loadNextSlice()`, `setSliceCriteria(...)`, `applySliceProgressRestore(...)`, `prepareSliceProgressRestore(...)` |
| WeakCharsPage | `loadWeakChars()`, `loadCharStatsBySort(...)` |
| ProfilePage | `loadTypingHistory()`, `setTrendRange(range)` |
| TextLoadHubPage | `loadFederatedEntries()`, `loadFederatedEntrySegment(...)`, `loadFederatedInlineEntry(...)`, `loadLocalArticles()`, `loadTrainers()`, `loadRandomWenlaiText()`, `requestAiText()`, `previewRepoManifest(url)`（异步经 `repoManifestPreviewed` 回投）, `refreshFederatedAll()`, `refreshFederatedSource(authority)`, `addRepo(url)`, `removeRepo(url)`, `setRepoEnabled(url, enabled)`, `confirmRepoTrust(url)`, `rejectRepoTrust(url)`, `getRepos()`（缓存摘要，无网络）, `getFederatedSourceStatuses()`, `setSourceRefreshOverride(authority, mode, seconds)`, `clearSourceRefreshOverride(authority)` |
| UploadTextPage | `uploadText(title, content, sourceKey, toLocal, toCloud)`（云端已移除，目标恒为本地；toCloud 参数保留兼容） |
| SettingsPage / settings/* | `updateWenlaiConfig(...)`, `loginWenlai(u, p)`, `logoutWenlai()`, `refreshWenlaiDifficulties()`, `refreshWenlaiCategories()`, `updateAiBaseUrl(...)`, `updateAiModel(...)`, `updateAiApiFormat(...)`, `updateAiMaxChars(...)`, `updateAiApiKey(...)`, `setScriptsEnabled(enabled)`, `checkForUpdate()`, `downloadAndInstallUpdate(version)`, `dismissUpdate()`, `loadFonts()`, `setReaderFontPath(path)`, `openFontFileDialog()`, `removeFont(name)`, `listAvailableInputDevices()`, `setKeyboardDevices(paths)`, `resetKeyboardAutoDetect()`, `loadZitiSchemes()`, `loadZitiScheme(name)` |
