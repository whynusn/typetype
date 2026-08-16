# Bridge Slot / Signal 速查
<!-- 状态: active | 最后验证: 2026-08-13 -->

> Bridge 是 QML 能看到的唯一后端门面。全局对象名：`appBridge`
> typetype-server 已移除（ADR-013）：登录/注册、服务端排行榜、远程文本列表、`base_url` 相关槽/信号/属性已删除。

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
| `textId` | `int` | 当前文本 ID（0=无；服务端 text_id 已移除，仅作本地段号/历史标识） |
| `defaultTextSourceKey` | `str` | 默认来源 key |
| `defaultTextTitle` | `str` | 默认来源标题 |
| `textSourceOptions` | `list[dict]` | 来源选项列表 |
| `isSpecialPlatform` | `bool` | 是否特殊平台（Wayland 下 evdev 监听可用） |
| `keyAccuracy` | `float` | 键准（%） |
| `wenlaiLoading` | `bool` | 晴发文加载中 |
| `wenlaiLoggedIn` | `bool` | 晴发文登录状态 |
| `wenlaiCurrentUser` | `str` | 晴发文当前用户显示名 |
| `isWenlaiActive` | `bool` | 当前文本是否来自晴发文 |
| `wenlaiSegmentMode` | `str` | 晴发文换段模式（manual/auto） |
| `wenlaiBaseUrl` | `str` | 晴发文服务地址 |
| `wenlaiLength` | `int` | 晴发文字数设置 |
| `wenlaiDifficultyLevel` | `int` | 晴发文难度等级（0=随机） |
| `wenlaiCategory` | `str` | 晴发文分类 |
| `wenlaiStrictLength` | `bool` | 晴发文是否精确字数 |
| `currentVersion` | `str` | 当前应用版本（`src/backend/version.py` `APP_VERSION`，constant） |
| `updateAvailable` | `bool` | 是否有可用更新 |
| `updateVersion` | `str` | 可用更新版本号 |

## Signals（QML 通过 Connections 监听）

| 信号 | 参数 | 触发时机 |
|------|------|---------|
| `textLoaded` | `(str text, int textId, str sourceLabel)` | 文本加载完成 |
| `textLoadFailed` | `(str message)` | 文本加载失败 |
| `textLoadingChanged` | 无 | 加载状态变化 |
| `typingEnded` | 无 | 打字结束 |
| `historyRecordUpdated` | `(dict record)` | 历史记录更新 |
| `weakestCharsLoaded` | `(list chars)` | 薄弱字加载完成 |
| `cursorPosChanged` | `(int pos)` | 光标位置变化 |
| `specialPlatformConfirmed` | `(bool confirmed)` | 特殊平台确认 |
| `textIdChanged` | 无 | textId 变化 |
| `backspaceChanged` | 无 | 退格次数变化 |
| `correctionChanged` | 无 | 回改次数变化 |
| `sliceModeChanged` | 无 | 进入/退出载文模式 |
| `sliceStatusChanged` | `(str status)` | 片进度更新（如 "载文模式: 第 3/5 片"） |
| `textContentLoaded` | `(int text_id, str content, str title)` | 联邦 inline 条目内容到达（text_id 恒为 0） |
| `keyAccuracyChanged` | 无 | 键准变化 |
| `wenlaiLoadFailed` | `(str message)` | 晴发文载文失败 |
| `wenlaiLoadingChanged` | 无 | 晴发文加载状态变化 |
| `wenlaiLoginResult` | `(bool success, str message)` | 晴发文登录结果 |
| `wenlaiLoginStateChanged` | 无 | 晴发文登录状态变化 |
| `wenlaiConfigChanged` | 无 | 晴发文配置或 active 状态变化 |
| `wenlaiDifficultiesLoaded` | `(list items)` | 晴发文难度列表加载完成 |
| `wenlaiCategoriesLoaded` | `(list items)` | 晴发文分类列表加载完成 |
| `uploadResult` | `(bool success, str message, int textId)` | 本地文本保存结果（云端上传已移除） |
| `updateCheckFinished` | `(bool available, str version, str error)` | 更新检查完成 |
| `updateDownloadProgress` | `(int percent)` | 更新下载进度（0-100） |
| `updateStatusChanged` | `(str status)` | 更新状态变化（downloading/extracting/installing/done 或错误） |

## Slots（QML 可调用的方法）

| 方法 | 参数 | 说明 |
|------|------|------|
| `handlePinyin` | `(str s)` | 处理拼音输入 |
| `handlePressed` | 无 | 处理按键事件 |
| `accumulateCorrection` | 无 | 累积回改次数（QML 文本删除时调用） |
| `accumulateBackspace` | 无 | 累积退格次数（QML 退格键按下时调用） |
| `setLowerPaneFocused` | `(bool focused)` | 设置输入区焦点状态 |
| `handleCommittedText` | `(str s, int growLength)` | 处理提交的文本 |
| `handleLoadedText` | `(QQuickTextDocument doc, str text="")` | 处理已加载的文本文档（可选 text 确保内容正确） |
| `setTextTitle` | `(str title)` | 设置文本标题 |
| `setTextId` | `(int textId)` | 设置文本 ID |
| `loadFullText` | `(str text, str source_key="")` | 全文载入（不分片） |
| `requestLoadText` | `(str sourceKey)` | 请求加载文本 |
| `loadTextFromClipboard` | 无 | 从剪贴板载文 |
| `uploadText` | `(str title, str content, str sourceKey, bool toLocal, bool toCloud)` | 保存文本到本地（云端上传已移除，toCloud 参数保留兼容） |
| `uploadTextFromFile` | `(str title, str filePath, str sourceKey, bool toLocal, bool toCloud)` | 从文件保存文本到本地（云端上传已移除） |
| `handleStartStatus` | `(bool status)` | 处理开始/停止状态 |
| `isStart` | → `bool` | 是否正在打字 |
| `isReadOnly` | → `bool` | 是否只读 |
| `getCursorPos` | → `int` | 获取光标位置 |
| `setCursorPos` | `(int newPos)` | 设置光标位置 |
| `getScoreMessage` | → `str` | 获取成绩摘要消息 |
| `getScorePlainText` | → `str` | 获取纯文本成绩摘要 |
| `copyScoreMessage` | 无 | 复制成绩到剪贴板 |
| `loadWeakChars` | `(int n=10, str sortMode="error_rate", dict weights=None)` | 加载薄弱字 |
| `requestShuffle` | 无 | 乱序当前文本 |
| `copyToClipboard` | `(str text)` | 复制文本到剪贴板 |
| `loadLocalArticles` | 无 | 异步扫描本地文库目录 |
| `loadLocalArticleSegment` | `(str articleId, int segmentIndex, int segmentSize)` | 异步加载本地文库指定段；普通分片只读取目标字符窗口 |
| `loadTrainers` | 无 | 异步扫描练单器词库目录 |
| `loadTrainerSegment` | `(str trainerId, int segmentIndex, int groupSize)` | 异步加载练单器指定分组 |
| `setupSliceMode` | `(str text, int sliceSize, int startSlice, float keyStrokeMin, int speedMin, int accuracyMin, int passCountMin, str onFailAction, bool autoDecreaseEnabled=false, float keyStrokeDecrease=0.0, int speedDecrease=0, int accuracyDecrease=0, str restoredProgress="", str title="")` | 初始化载文模式（分片），分片并加载第 startSlice 片 |
| `collectSliceResult` | 无 | 收集当前片的 SessionStat 快照 |
| `isLastSlice` | → `bool` | 当前片是否为最后一片 |
| `loadNextSlice` | 无 | 载入下一片 |
| `shouldRetype` | → `bool` | 检查当前片成绩是否触发重打条件 |
| `handleSliceRetype` | 无 | 根据重打配置自动处理重打（内部判断 shuffle） |
| `shuffleCurrentSlice` | 无 | 乱序当前片并载入 |
| `buildAggregateScore` | → `str` | 计算聚合成绩，返回格式化消息 |
| `copyAggregateScore` | 无 | 复制聚合成绩到剪贴板 |
| `exitSliceMode` | 无 | 退出载文模式，清理状态 |
| `getSliceStatus` | → `str` | 返回当前片进度摘要 |
| `getLastSliceStats` | → `dict` | 获取最近一次分片完成时的 score_data 快照 |
| `getLocalTextContent` | `(str source_key)` → `str` | 同步读取本地文本内容（供载文 Dialog 离线预览） |
| `loadPrevSlice` | 无 | 载入上一片 |
| `getOnFailAction` | → `str` | 返回当前未达标处理动作 |
| `checkSliceResult` | → `str` | 检查当前片结果：fail/pass/advance |
| `handleSliceRetypeNoDecrease` | 无 | 重打当前片，不触发降击（连达标未满场景） |
| `getSliceCriteria` | → `str` | 返回当前达标条件文字（含降击后更新） |
| `hasSliceProgress` | `(str progressKey, str title="")` → `bool` | 查询指定 key 是否有保存的分片进度，title 用于旧格式回退 |
| `getSliceProgressInfo` | `(str progressKey, str title="")` → `str` | 返回 JSON 格式的进度详情 |
| `applySliceProgressRestore` | `(str progressKey, bool restore, str title="")` → `str` | 处理恢复弹窗结果，返回进度 JSON 或空字符串 |
| `prepareSliceProgressRestore` | `(str progressKey, str title="")` | source-based 路径：预加载进度供 segment loader 恢复 |
| `loadSliceMetricsPrefs` | → `dict` | 加载上次保存的分片指标偏好设置 |
| `saveSliceMetricsPrefs` | `(float keyStrokeMin, int speedMin, int accuracyMin, int passCountMin, str onFailAction, bool autoDecreaseEnabled, float keyStrokeDecrease, int speedDecrease, int accuracyDecrease)` | 保存分片指标偏好设置 |
| `getTextSliceProgress` | `(str text)` → `dict` | 查询指定文本的分片进度历史记录 |
| `saveTextSliceProgress` | `(str text, str title, dict progress)` | 保存指定文本的分片进度 |
| `loginWenlai` | `(str username, str password)` | 登录晴发文 |
| `logoutWenlai` | 无 | 退出晴发文 |
| `loadRandomWenlaiText` | 无 | 加载晴发文随机文本 |
| `loadNextWenlaiSegment` | 无 | 加载晴发文下一段 |
| `loadNextWenlaiSegmentWithScore` | 无 | 复制当前成绩，加载下一段，成功后复制“成绩 + 下一段发文内容” |
| `loadPrevWenlaiSegment` | 无 | 加载晴发文上一段 |
| `refreshWenlaiDifficulties` | 无 | 刷新晴发文难度列表 |
| `refreshWenlaiCategories` | 无 | 刷新晴发文分类列表 |
| `updateWenlaiConfig` | `(str baseUrl, int length, int difficultyLevel, str category, str segmentMode, bool strictLength)` | 更新并持久化晴发文配置 |
| `checkForUpdate` | 无 | 手动检查更新（强制） |
| `downloadAndInstallUpdate` | `(str version)` | 下载并安装指定版本 |
| `dismissUpdate` | 无 | 关闭更新提示 |

### OTT Repo 联邦目录 Slot（Phase 1）

| 方法 | 参数 | 说明 |
|------|------|------|
| `getRepos` | → `list[dict]` | 返回订阅摘要列表（同步，走 manifest 缓存） |
| `addRepo` | `(str url)` | 添加源仓库订阅（ott-repo.json URL） |
| `removeRepo` | `(str url)` | 移除订阅并清除其 manifest 缓存 |
| `setRepoEnabled` | `(str url, bool enabled)` | 启用/禁用订阅 |
| `confirmRepoTrust` | `(str url)` | 确认信任订阅（TOFU pending → verified） |
| `rejectRepoTrust` | `(str url)` | 拒绝信任订阅（pending → unverified） |
| `refreshRepos` | 无 | 重新加载所有订阅的 manifest 摘要（后台 Worker） |
| `refreshRepo` | `(str url)` | 强制刷新单条订阅的 manifest（后台 Worker） |
| `loadFederatedEntries` | 无 | 加载联邦聚合的全部条目（后台 Worker） |
| `loadFederatedEntrySegment` | `(str authority, str entryId, str revisionId, int segmentIndex, int segmentSize, int totalChars, int sourceSegmentSize, str title)` | 从联邦聚合加载 OTT 分段文本 |
| `loadFederatedInlineEntry` | `(str authority, str entryId, str revisionId, str title)` | 从联邦聚合加载 inline 内容（规则/脚本源） |
| `setScriptsEnabled` | `(bool enabled)` | 更新 ott-script（L3）开关并持久化 |

对应 Properties：`reposLoading`（bool）、`federatedEntriesLoading`（bool）、`scriptsEnabled`（bool）。

对应 Signals：`reposChanged(list)`、`reposLoadFailed(str)`、`registryFederatedEntriesLoaded(list)`、`registryFederatedEntriesLoadFailed(str)`。

## 载文模式 Properties

| 属性 | 类型 | 说明 |
|------|------|------|
| `sliceMode` | `bool` | 是否处于载文模式 |
| `totalSliceCount` | `int` | 总片数 |
| `sliceIndex` | `int` | 当前片索引（1-based） |
| `slicePassCount` | `int` | 当前片已通过次数 |
