# Bridge Slot / Signal 速查

> Bridge 是 QML 能看到的唯一后端门面。全局对象名：`appBridge`

## Properties（QML 可直接绑定）

| 属性 | 类型 | 说明 |
|------|------|------|
| `typeSpeed` | `float` | 当前速度（字/分） |
| `keyStroke` | `float` | 击键（击/秒） |
| `codeLength` | `float` | 码长（击/字） |
| `charNum` | `str` | 已打字数（显示用） |
| `wrongNum` | `int` | 错误字数 |
| `backspace` | `int` | 退格键按下次数 |
| `correction` | `int` | 回改次数 |
| `totalTime` | `float` | 总用时（秒） |
| `textReadOnly` | `bool` | 是否只读（未载文时禁止打字） |
| `textLoading` | `bool` | 文本加载中 |
| `loggedin` | `bool` | 登录状态 |
| `currentUser` | `str` | 当前用户名 |
| `userNickname` | `str` | 当前用户昵称 |
| `textId` | `int` | 当前文本 ID（0=本地文本） |
| `defaultTextSourceKey` | `str` | 默认来源 key |
| `defaultTextTitle` | `str` | 默认来源标题 |
| `textSourceOptions` | `list[dict]` | 来源选项列表 |
| `uploadTextSourceOptions` | `list[dict]` | 上传目标来源选项 |
| `leaderboardLoading` | `bool` | 排行榜加载中 |
| `textListLoading` | `bool` | 文本列表加载中 |
| `rankingSourceOptions` | `list[dict]` | 排行榜来源选项列表 |
| `isSpecialPlatform` | `bool` | 是否特殊平台（需确认） |

## Signals（QML 通过 Connections 监听）

| 信号 | 参数 | 触发时机 |
|------|------|---------|
| `textLoaded` | `(str text, int textId, str sourceLabel)` | 文本加载完成 |
| `textLoadFailed` | `(str message)` | 文本加载失败 |
| `textLoadingChanged` | 无 | 加载状态变化 |
| `typingEnded` | 无 | 打字结束 |
| `historyRecordUpdated` | `(dict record)` | 历史记录更新 |
| `loginResult` | `(bool success, str message)` | 登录结果 |
| `registerResult` | `(bool success, str message)` | 注册结果 |
| `loginStateInitialized` | `(bool loggedIn)` | 启动时登录态初始化 |
| `loggedinChanged` | 无 | 登录状态变化 |
| `userInfoChanged` | 无 | 用户信息变化 |
| `weakestCharsLoaded` | `(list chars)` | 薄弱字加载完成 |
| `leaderboardLoaded` | `(dict data)` | 排行榜加载完成 |
| `leaderboardLoadFailed` | `(str message)` | 排行榜加载失败 |
| `leaderboardLoadingChanged` | 无 | 排行榜加载状态变化 |
| `catalogLoaded` | `(list catalog)` | 来源目录加载完成 |
| `catalogLoadFailed` | `(str message)` | 来源目录加载失败 |
| `textListLoaded` | `(list texts)` | 文本列表加载完成 |
| `textListLoadFailed` | `(str message)` | 文本列表加载失败 |
| `textListLoadingChanged` | 无 | 文本列表加载状态变化 |
| `uploadResult` | `(bool success, str message, int textId)` | 上传结果 |
| `tokenExpired` | 无 | token 过期 |
| `cursorPosChanged` | `(int pos)` | 光标位置变化 |
| `specialPlatformConfirmed` | `(bool confirmed)` | 特殊平台确认 |
| `textIdChanged` | 无 | textId 变化 |
| `backspaceChanged` | 无 | 退格次数变化 |
| `correctionChanged` | 无 | 回改次数变化 |

## Slots（QML 可调用的方法）

| 方法 | 参数 | 说明 |
|------|------|------|
| `handlePinyin` | `(str s)` | 处理拼音输入 |
| `handlePressed` | 无 | 处理按键事件 |
| `accumulateCorrection` | 无 | 累积回改次数（QML 文本删除时调用） |
| `accumulateBackspace` | 无 | 累积退格次数（QML 退格键按下时调用） |
| `setLowerPaneFocused` | `(bool focused)` | 设置输入区焦点状态 |
| `handleCommittedText` | `(str s, int growLength)` | 处理提交的文本 |
| `handleLoadedText` | `(QQuickTextDocument doc)` | 处理已加载的文本文档 |
| `setTextTitle` | `(str title)` | 设置文本标题 |
| `setTextId` | `(int textId)` | 设置文本 ID |
| `requestLoadText` | `(str sourceKey)` | 请求加载文本 |
| `loadTextFromClipboard` | 无 | 从剪贴板载文 |
| `uploadText` | `(str title, str content, str sourceKey, bool toLocal, bool toCloud)` | 上传文本 |
| `handleStartStatus` | `(bool status)` | 处理开始/停止状态 |
| `isStart` | → `bool` | 是否正在打字 |
| `isReadOnly` | → `bool` | 是否只读 |
| `getCursorPos` | → `int` | 获取光标位置 |
| `setCursorPos` | `(int newPos)` | 设置光标位置 |
| `getScoreMessage` | → `str` | 获取成绩摘要消息 |
| `copyScoreMessage` | 无 | 复制成绩到剪贴板 |
| `login` | `(str username, str password)` | 登录 |
| `register` | `(str username, str password, str nickname)` | 注册 |
| `logout` | 无 | 登出 |
| `checkTokenStatus` | 无 | 检查 token 状态 |
| `loadWeakChars` | `(int n=10, str sortMode="error_rate", dict weights=None)` | 加载薄弱字 |
| `loadLeaderboard` | `(str sourceKey)` | 加载来源最新排行榜 |
| `loadLeaderboardByTextId` | `(int textId)` | 按文本 ID 加载排行榜 |
| `loadTextList` | `(str sourceKey)` | 加载来源下文本列表 |
| `loadCatalog` | 无 | 加载来源目录 |
| `refreshCatalog` | 无 | 强制刷新来源目录 |
| `requestShuffle` | 无 | 乱序当前文本 |
| `copyToClipboard` | `(str text)` | 复制文本到剪贴板 |
