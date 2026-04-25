# QML 页面与组件速查

> 所有 QML 文件位于 `src/qml/` 下。

## 页面清单（导航入口）

| 文件 | 导航标题 | 依赖信号 |
|------|---------|---------|
| `pages/TypingPage.qml` | 跟打 | `textLoaded`, `textLoadFailed`, `uploadResult`, `loggedinChanged` |
| `pages/WeakCharsPage.qml` | 薄弱字 | `weakestCharsLoaded` |
| `pages/TextLeaderboardPage.qml` | 文本排行 | `catalogLoaded`, `textListLoaded`, `leaderboardLoaded`, `leaderboardLoadFailed` |
| `pages/DailyLeaderboard.qml` | （保留但导航已移除） | `leaderboardLoaded`, `leaderboardLoadFailed` |
| `pages/WeeklyLeaderboard.qml` | （保留但导航已移除，建设中） | `leaderboardLoaded`, `leaderboardLoadFailed` |
| `pages/AllTimeLeaderboard.qml` | （保留但导航已移除，建设中） | `leaderboardLoaded`, `leaderboardLoadFailed` |
| `pages/UploadTextPage.qml` | 上传文本 | `uploadResult`, `loggedinChanged` |
| `pages/ProfilePage.qml` | 个人中心 | `loginResult`, `registerResult`, `loggedinChanged`, `userInfoChanged`, `loginStateInitialized` |
| `pages/SettingsPage.qml` | 设置 | 无 |

## TypingPage 子组件

| 文件 | 职责 |
|------|------|
| `typing/ToolLine.qml` | 工具栏（载文/剪贴板/重打/排行榜按钮） |
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

## QML → Bridge 调用速查

| QML 页面 | 调用的 Bridge 方法 |
|----------|-------------------|
| TypingPage | `requestLoadText(key)`, `loadTextFromClipboard()`, `setTextId(id)`, `setTextTitle(t)`, `handleLoadedText(doc, text)`, `handleStartStatus(s)`, `getScoreMessage()`, `setTextId(0)` |
| TypingPage (载文模式) | `collectSliceResult()`, `isLastSlice()`, `buildAggregateScore()`, `exitSliceMode()`, `shouldRetype()`, `handleSliceRetype()`, `loadNextSlice()` |
| SliceConfigDialog | `loadCatalog()`, `loadTextList(key)`, `getTextContentById(id)`, `loadFullText(text, srcKey)`, `setupSliceMode(text, size, ...)` |
| WeakCharsPage | `loadWeakChars()` |
| TextLeaderboardPage | `loadCatalog()`, `loadTextList(key)`, `loadLeaderboardByTextId(id)`, `loadLeaderboard(key)` |
| DailyLeaderboard | `loadLeaderboard("jisubei")`, `copyToClipboard(text)` |
| UploadTextPage | `uploadText(title, content, sourceKey, toLocal, toCloud)` |
| ProfilePage | `login(u, p)`, `register(u, p, n)`, `logout()`, `checkTokenStatus()` |
| LeaderboardPanel | `loadLeaderboardByTextId(id)`, `copyToClipboard(text)` |
