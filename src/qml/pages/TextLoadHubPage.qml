import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"
import "../components"
import "../helpers/TextSourceBehaviors.js" as SrcBehav

/**
 * 统一载文中心。
 *
 * 将本地文库、开源文库、练单器、晴发文、AI 推荐、自定义 6 种来源收敛到单一页面。
 * 顶部为 RinUI Segmented 来源切换，左侧为对应列表/输入，右侧为统一的预览 + 切片设置 + 操作按钮。
 * 开源文库按订阅源分组展示联邦聚合条目（RepoEntriesPanel，组头可管理该源），
 * 不再有独立订阅管理子页面（源配置经组头弹窗 RepoConfigDialog 完成）。
 */
FluentPage {
    id: root
    title: qsTr("载文")
    horizontalPadding: 20
    wrapperWidth: 1200

    property bool active: false
    property string initialSource: ""
    property string currentSource: initialSource || "local"

    // ---- 来源定义 ----
    readonly property var sourceKeys: ["local", "repos", "trainer", "wenlai", "ai", "custom"]
    readonly property var sourceLabels: [
        qsTr("本地文库"),
        qsTr("开源文库"),
        qsTr("练单器"),
        qsTr("晴发文"),
        qsTr("AI 推荐"),
        qsTr("自定义")
    ]
    readonly property var sourceIcons: [
        "ic_fluent_library_20_regular",
        "ic_fluent_cloud_arrow_down_20_regular",
        "ic_fluent_apps_list_detail_20_regular",
        "ic_fluent_book_20_regular",
        "ic_fluent_sparkle_20_regular",
        "ic_fluent_edit_20_regular"
    ]

    readonly property int currentSourceIndex: sourceKeys.indexOf(currentSource)
    // 有右侧预览/切片面板的来源；晴发文/AI 为全宽全出血布局
    readonly property bool isListSource: ["local", "repos", "trainer", "custom"].indexOf(currentSource) >= 0

    // ---- 响应式断点 ----
    readonly property bool wideMode: width >= 760

    // ---- 列表数据 ----
    property var localItems: []
    property var trainerItems: []

    // ---- 当前选中项 ----
    property var selectedItem: null
    property string previewContent: ""
    property string statusMessage: ""
    property string errorMessage: ""
    property bool sliceModeChecked: true
    property bool hasProgress: false
    property bool catalogLoading: false  // 目录加载状态
    property var federatedEntries: []    // 联邦聚合的条目（所有 repo 的条目）
    property string reposEntriesError: ""  // 开源文库条目加载错误（喂给 RepoEntriesPanel.errorText）
    property string localListError: ""     // 本地文库列表加载错误（喂给 TextSourceListPanel.errorText）
    property string trainerListError: ""   // 练单器词库列表加载错误（同上）
    property var federatedSourceStatuses: ({})  // authority -> {state,message,checked_at}
    property bool federatedContentLoading: false  // 联邦条目载文请求进行中（载入跟打按钮 Busy）
    property bool repoManifestPreviewLoading: false

    // ---- 初始化 / 激活 ----
    onActiveChanged: {
        if (active) {
            var sourceChanged = false
            if (initialSource && initialSource !== currentSource) {
                currentSource = initialSource
                sourceChanged = true
            }
            initialSource = ""
            // currentSource 变化时 onCurrentSourceChanged 已触发 loadCurrentSource，
            // 仅当来源未变时才在此显式加载，避免双重加载
            if (!sourceChanged) loadCurrentSource()
            loadSlicePrefs()
        }
    }

    onCurrentSourceChanged: {
        selectedItem = null
        previewContent = ""
        errorMessage = ""
        statusMessage = ""
        reposEntriesError = ""
        localListError = ""
        trainerListError = ""
        hasProgress = false
        if (active) loadCurrentSource()
    }

    // 通知走页面级函数：Connections 不是 Item，在其作用域里写 Window.window
    // 会让 Qt 对**每次**信号分发报一次警告（静态看合法，只有真机跑才显形）
    function _notifySuccess(message, duration) {
        if (Window.window && Window.window.appNotificationManager)
            Window.window.appNotificationManager.show(
                Severity.Success, "", message, duration)
    }

    function loadCurrentSource() {
        if (!appBridge) return
        // 开源文库先同步加载 per-source 健康状态（零网络），再分派列表
        if (currentSource === "repos") {
            root.federatedSourceStatuses = appBridge.getFederatedSourceStatuses() || {}
        }
        // 注册表分派当前来源的列表加载（bridge 调用 + 状态消息）
        var msg = SrcBehav.loadList(appBridge, currentSource)
        if (msg) statusMessage = msg
    }

    function loadSlicePrefs() {
        if (!appBridge) return
        var prefs = appBridge.loadSliceMetricsPrefs()
        if (prefs && prefs.key_stroke_min !== undefined) {
            sliceCriteriaPanel.keyStrokeMinValue = prefs.key_stroke_min
            sliceCriteriaPanel.speedMinValue = prefs.speed_min || 100
            sliceCriteriaPanel.accuracyMinValue = prefs.accuracy_min || 95
            sliceCriteriaPanel.passCountMinValue = prefs.pass_count_min || 1
            if (prefs.on_fail_action === "shuffle") sliceCriteriaPanel.onFailActionValue = "shuffle"
            else if (prefs.on_fail_action === "retype") sliceCriteriaPanel.onFailActionValue = "retype"
            else sliceCriteriaPanel.onFailActionValue = "none"
            sliceCriteriaPanel.autoDecreaseEnabled = prefs.auto_decrease_enabled || false
            sliceCriteriaPanel.keyStrokeDecreaseValue = prefs.key_stroke_decrease || 0.0
            sliceCriteriaPanel.speedDecreaseValue = prefs.speed_decrease || 0
            sliceCriteriaPanel.accuracyDecreaseValue = prefs.accuracy_decrease || 0
        }
    }

    // ---- 列表同步（数据分派统一走 TextSourceBehaviors）----

    // 把同步结果写入当前来源的列表 property
    function _syncToCurrentList(rawData) {
        var propName = SrcBehav.itemsListPropertyName(currentSource)
        if (!propName) return
        var result = SrcBehav.syncItems(currentSource, rawData)
        root[propName] = result.items
        statusMessage = result.statusMessage
    }

    // ---- 选择事件 ----
    property var _lastSelectedRaw: null  // 去重守卫：防止重复点击同一项

    function selectListItem(source, originalIndex) {
        // 注册表分派当前来源的列表属性名
        var propName = SrcBehav.itemsListPropertyName(source)
        var items = propName ? root[propName] : []
        if (originalIndex < 0 || originalIndex >= items.length) {
            selectedItem = null
            _lastSelectedRaw = null
            return
        }
        var raw = items[originalIndex].raw
        // 去重：点击同一项不做重复操作
        if (raw === _lastSelectedRaw && source === currentSource) return
        _lastSelectedRaw = raw

        selectedItem = raw
        previewContent = ""
        errorMessage = ""
        statusMessage = qsTr("已选择：%1").arg(itemDisplayTitle())
        hasProgress = false

        // needsContentPrefetch == true 的来源点选即异步拉取内容预览
        if (SrcBehav.capabilities[source].needsContentPrefetch && selectedItem && appBridge) {
            var pid = SrcBehav.previewId(source, selectedItem)
            if (pid) {
                SrcBehav.startPreview(appBridge, source, pid)
            } else {
                checkProgress()
            }
        } else {
            checkProgress()
        }
    }

    // ---- 信息卡展示（数据统一由 TextSourceBehaviors 分派） ----
    function itemDisplayTitle() {
        return SrcBehav.cardTitle(currentSource, selectedItem, previewContent,
                                  textLoadPanel ? textLoadPanel.selectedSourceLabel : "")
    }
    function itemDisplayId() {
        return null
    }
    function itemDisplayCharCount() {
        return SrcBehav.cardCharCount(currentSource, selectedItem, previewContent,
                                       textLoadPanel ? textLoadPanel.contentLength : 0)
    }
    function itemDisplayContent() {
        return SrcBehav.cardContent(currentSource, selectedItem, previewContent,
                                     textLoadPanel ? textLoadPanel.contentText : "")
    }

    // ---- 进度 key / identifier（数据统一由 TextSourceBehaviors 分派） ----
    function progressKeyType() {
        return SrcBehav.progressKeyAndId(currentSource, selectedItem, previewContent,
                                         textLoadPanel ? textLoadPanel.contentText : "").key
    }
    function progressIdentifier() {
        return SrcBehav.progressKeyAndId(currentSource, selectedItem, previewContent,
                                         textLoadPanel ? textLoadPanel.contentText : "").identifier
    }

    function checkProgress() {
        if (!appBridge || !selectedItem) {
            hasProgress = false
            return
        }
        var id = progressIdentifier()
        if (id && id.length > 0) {
            hasProgress = appBridge.hasSliceProgress(appBridge.getProgressKey(progressKeyType(), id), itemDisplayTitle())
        } else {
            hasProgress = false
        }
    }

    // 自定义来源的字数。**必须是 QML 属性而不是 JS 回调**：canLoad() 一旦
    // 经由 .pragma library 里的函数指针读字数，readyForLoad 的绑定就抓不到
    // 对 contentText 的依赖——粘贴完文本「载入跟打」仍是灰的，只有切走再切回来
    // （扰动 currentSource）才会刷新。回归场景：app-slice-progression。
    readonly property int customTextLength: textLoadPanel ? textLoadPanel.contentLength : 0

    function continueLastProgress() {
        if (currentSource === "custom") {
            var text = textLoadPanel.contentText
            if (!text) return
            var infoJson = appBridge.getSliceProgressInfo(appBridge.getProgressKey("custom_text", text), textLoadPanel.selectedSourceLabel || "")
            if (!infoJson) { loadSelectedItem(); return }
            progressRestoreDialog.progressInfo = JSON.parse(infoJson)
            progressRestoreDialog._source = currentSource
            progressRestoreDialog._restoreId = text
            progressRestoreDialog._restoreTitle = textLoadPanel.selectedSourceLabel || ""
            progressRestoreDialog.open()
            return
        }
        if (!selectedItem) { errorMessage = qsTr("请先选择一个项目"); return }
        var id = progressIdentifier()
        var title = itemDisplayTitle()
        var infoJson = appBridge.getSliceProgressInfo(appBridge.getProgressKey(progressKeyType(), id), title)
        if (!infoJson) { loadSelectedItem(); return }
        progressRestoreDialog._source = currentSource
        progressRestoreDialog._restoreId = id
        progressRestoreDialog._restoreTitle = title
        progressRestoreDialog.progressInfo = JSON.parse(infoJson)
        progressRestoreDialog.open()
    }

    // ---- 切片参数 ----
    function setupSliceCriteria(rp) {
        if (!appBridge) return
        var s = rp || {}
        var criteriaOn = s.condition_on !== undefined ? s.condition_on : sliceCriteriaPanel.conditionChecked
        appBridge.saveSliceMetricsPrefs(
            criteriaOn ? (s.key_stroke_min || sliceCriteriaPanel.keyStrokeMinValue) : 0,
            criteriaOn ? (s.speed_min || sliceCriteriaPanel.speedMinValue) : 0,
            criteriaOn ? (s.accuracy_min || sliceCriteriaPanel.accuracyMinValue) : 0,
            criteriaOn ? (s.pass_count_min || sliceCriteriaPanel.passCountMinValue) : 1,
            s.on_fail_action || sliceCriteriaPanel.onFailActionValue,
            s.auto_decrease_enabled !== undefined ? s.auto_decrease_enabled : sliceCriteriaPanel.autoDecreaseEnabled,
            s.key_stroke_decrease || sliceCriteriaPanel.keyStrokeDecreaseValue,
            s.speed_decrease || sliceCriteriaPanel.speedDecreaseValue,
            s.accuracy_decrease || sliceCriteriaPanel.accuracyDecreaseValue
        )
        appBridge.setSliceCriteria(
            criteriaOn ? (s.key_stroke_min || sliceCriteriaPanel.keyStrokeMinValue) : 0,
            criteriaOn ? (s.speed_min || sliceCriteriaPanel.speedMinValue) : 0,
            criteriaOn ? (s.accuracy_min || sliceCriteriaPanel.accuracyMinValue) : 0,
            criteriaOn ? (s.pass_count_min || sliceCriteriaPanel.passCountMinValue) : 1,
            criteriaOn ? (s.on_fail_action || sliceCriteriaPanel.onFailActionValue) : "none",
            s.advance_mode || sliceCriteriaPanel.advanceModeValue,
            s.full_shuffle !== undefined ? s.full_shuffle : sliceSettingsPanel.fullShuffleChecked,
            s.auto_decrease_enabled !== undefined ? s.auto_decrease_enabled : sliceCriteriaPanel.autoDecreaseEnabled,
            s.key_stroke_decrease || sliceCriteriaPanel.keyStrokeDecreaseValue,
            s.speed_decrease || sliceCriteriaPanel.speedDecreaseValue,
            s.accuracy_decrease || sliceCriteriaPanel.accuracyDecreaseValue
        )
    }

    function navigateToTyping() {
        if (Window.window && Window.window.navigationView)
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))
    }

    // 当前来源的加载状态（来源感知，不再把其它来源的 loading 混进来）
    function currentSourceLoading() {
        return SrcBehav.isLoading(currentSource, appBridge, root)
    }

    // 统一的「就绪」表达：当前来源已加载完成 + 已满足 canLoad 前置条件
    // 供「载入跟打」按钮的 enabled / highlighted 绑定，避免按钮颜色受无关来源 API 牵制
    property bool readyForLoad: canLoad() && !currentSourceLoading() && !sliceCriteriaPanel.validationMessage

    function loadSelectedItem(rp) {
        if (!appBridge) return
        startTypingFromRequest(buildLaunchRequest(), rp)
    }

    function buildLaunchRequest() {
        var capability = SrcBehav.capabilities[currentSource]
        if (!capability) return null

        if (currentSource === "custom") {
            var customText = textLoadPanel.contentText
            if (!customText) { errorMessage = qsTr("请输入文本"); return null }
            return {
                source: "custom",
                launchKind: capability.launchKind,
                text: customText,
                sourceKey: textLoadPanel.selectedSourceKey || "custom",
                title: textLoadPanel.selectedSourceLabel || qsTr("自定义文本"),
                textId: 0
            }
        }

        if (!selectedItem) { errorMessage = qsTr("请选择一个项目"); return null }

        if (currentSource === "local") {
            var id = SrcBehav.articleId(selectedItem)
            if (!id) { errorMessage = qsTr("文章缺少 ID"); return null }
            return {
                source: "local",
                launchKind: capability.launchKind,
                identifier: id,
                title: itemDisplayTitle(),
                fullSize: SrcBehav.articleCharCount(selectedItem)
            }
        }

        if (currentSource === "trainer") {
            var tid = SrcBehav.trainerId(selectedItem)
            if (!tid) { errorMessage = qsTr("词库缺少 ID"); return null }
            return {
                source: "trainer",
                launchKind: capability.launchKind,
                identifier: tid,
                title: itemDisplayTitle(),
                fullSize: SrcBehav.trainerEntryCount(selectedItem)
            }
        }

        if (currentSource === "repos") {
            var entry = selectedItem
            var authority = entry._authority || entry.authority || ""
            var entryId = entry.entry_id || ""
            var revisionId = entry.current_revision_id || entry.revision_id || "v1"
            var totalChars = entry.char_count || entry.charCount || 0
            var title = entry.title || entry.source_label || qsTr("联邦文本")
            // 后端字段为 segment_size_hint（旧 source_segment_size / segment_size 键从未存在）
            var sourceSegmentSize = entry.segment_size_hint || 1000
            if (!authority || !entryId) {
                errorMessage = qsTr("条目缺少 authority 或 entry_id")
                return null
            }
            return {
                source: "repos",
                launchKind: capability.launchKind,
                authority: authority,
                entryId: entryId,
                revisionId: revisionId,
                title: title,
                totalChars: totalChars,
                sourceSegmentSize: sourceSegmentSize,
                contentMode: entry.content_mode || "inline"
            }
        }

        return null
    }

    function startTypingFromRequest(request, rp) {
        if (!appBridge || !request) return
        if (!rp) appBridge.clearPendingRestore()

        if (request.launchKind === "materialized_text") {
            startMaterializedText(request, rp)
        } else if (request.launchKind === "segmented_source") {
            startSegmentedSource(request, rp)
        } else if (request.launchKind === "federated_entry") {
            startFederatedEntry(request, rp)
        } else {
            errorMessage = qsTr("不支持的载文方式")
        }
    }

    function startSegmentedSource(request, rp) {
        var fullText = !root.sliceModeChecked
        var size = sliceSettingsPanel.sliceSize
        var index = sliceSettingsPanel.startSlice
        index = Math.max(1, Math.min(index, sliceSettingsPanel.totalSlices))
        if (fullText) { size = request.fullSize; index = 1 }

        setupSliceCriteria(rp)
        navigateToTyping()
        Qt.callLater(function() {
            appBridge.queueTextSession({
                source: request.source,
                identifier: request.identifier,
                segmentIndex: index,
                segmentSize: size
            })
        })
    }

    function startFederatedEntry(request, rp) {
        if (!appBridge || !request) return
        /* segmented：先进入打字页再加载分段（与 startSegmentedSource 一致），
           后端同步直发 textLoaded 后由 TypingPage applyLoadedText 落地 */
        if (request.contentMode === "segmented") {
            setupSliceCriteria(rp)
            navigateToTyping()
            root.federatedContentLoading = true
            federatedLoadTimeoutTimer.restart()
            Qt.callLater(function() {
                appBridge.loadFederatedEntrySegment(
                    request.authority, request.entryId, request.revisionId,
                    1,
                    root.sliceModeChecked ? sliceSettingsPanel.sliceSize : request.totalChars,
                    request.totalChars, request.sourceSegmentSize, request.title
                )
            })
            return
        }
        /* inline（规则/脚本/桥接源）同步读取快照/拉取内容，后端直发
           textLoaded（镜像 loadFullText 链路）：先进入打字页再载文，
           busy 由 onTextLoaded 清除。开启分片设置时经 sliceOpts 由后端
           本地切分（setupSliceMode），进度键 ott:{authority}:{entry_id}@{revision_id} */
        root.federatedContentLoading = true
        federatedLoadTimeoutTimer.restart()
        if (root.sliceModeChecked) setupSliceCriteria(rp)
        navigateToTyping()
        Qt.callLater(function() {
            var s = rp || {}
            var sliceOpts = {}
            if (root.sliceModeChecked) {
                sliceOpts = {
                    slice_size: sliceSettingsPanel.sliceSize,
                    start_slice: s.current_slice > 0 ? s.current_slice : sliceSettingsPanel.startSlice,
                    restored_progress: rp ? JSON.stringify(rp) : ""
                }
            }
            appBridge.loadFederatedInlineEntry(
                request.authority, request.entryId, request.revisionId, request.title, sliceOpts
            )
        })
    }

    function startMaterializedText(request, rp) {
        if (!appBridge || !request) return
        if (!request.text) return

        var s = rp || {}
        var fullText = !root.sliceModeChecked
        var sliceSize = s.slice_size > 0 ? s.slice_size : sliceSettingsPanel.sliceSize
        var startSlice = s.current_slice > 0 ? s.current_slice : sliceSettingsPanel.startSlice
        if (fullText) { sliceSize = request.text.length; startSlice = 1 }

        setupSliceCriteria(rp)
        navigateToTyping()
        Qt.callLater(function() {
            if (fullText) appBridge.loadFullText(request.text, request.sourceKey, request.title, request.textId || 0)
            else appBridge.setupSliceMode(request.text, sliceSize, startSlice,
                sliceCriteriaPanel.keyStrokeMinValue, sliceCriteriaPanel.speedMinValue,
                sliceCriteriaPanel.accuracyMinValue, sliceCriteriaPanel.passCountMinValue,
                sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.onFailActionValue : "none",
                sliceCriteriaPanel.autoDecreaseEnabled, sliceCriteriaPanel.keyStrokeDecreaseValue,
                sliceCriteriaPanel.speedDecreaseValue, sliceCriteriaPanel.accuracyDecreaseValue,
                rp ? JSON.stringify(rp) : "", request.title)
        })
    }

    function startCustomTyping(rp) {
        startTypingFromRequest(buildLaunchRequest(), rp)
    }

    function canLoad() {
        if (!appBridge) return false
        // custom 来源字数校验（依赖 textLoadPanel，留在 hub）
        if (currentSource === "custom") return customTextLength > 0
        // local / trainer / repos 选中即可载文（repos 不依赖预览内容）
        return selectedItem !== null
    }

    function canContinue() {
        return hasProgress && canLoad()
    }

    // ---- 联邦载文超时兜底 ----
    // 与后端 RegistryAdapter._ENTRIES_REFRESH_TIMEOUT_S=45 对齐：极端路径（DNS 挂起等）
    // 下 textLoaded/textLoadFailed 可能不到达，federatedContentLoading 会永转。
    // 单发定时器；操作提前完成时在常驻 Connections 中停止，陈旧超时经状态检查忽略。
    Timer {
        id: federatedLoadTimeoutTimer
        interval: 45000
        repeat: false
        onTriggered: {
            if (root.federatedContentLoading) {
                root.federatedContentLoading = false
                root.errorMessage = qsTr("载文超时，请检查网络后重试")
                root.statusMessage = ""
            }
        }
    }

    // ===================================================================
    // UI
    // ===================================================================

    ColumnLayout {
        id: container
        width: parent.width
        spacing: 16

        // ---- 顶部来源切换（RinUI Segmented）----
        Segmented {
            id: sourceSegmented
            currentIndex: root.currentSourceIndex

            SegmentedItem { text: qsTr("本地文库"); icon.name: "ic_fluent_library_20_regular" }
            SegmentedItem { text: qsTr("开源文库"); icon.name: "ic_fluent_cloud_arrow_down_20_regular" }
            SegmentedItem { text: qsTr("练单器"); icon.name: "ic_fluent_apps_list_detail_20_regular" }
            SegmentedItem { text: qsTr("晴发文"); icon.name: "ic_fluent_book_20_regular" }
            SegmentedItem { text: qsTr("AI 推荐"); icon.name: "ic_fluent_sparkle_20_regular" }
            SegmentedItem { text: qsTr("自定义"); icon.name: "ic_fluent_edit_20_regular" }

            onCurrentIndexChanged: {
                if (currentIndex >= 0 && currentIndex < root.sourceKeys.length)
                    root.currentSource = root.sourceKeys[currentIndex]
            }
        }

        // ---- 主体 ----
        GridLayout {
            Layout.fillWidth: true
            /* FluentPage 内容区高度由内容驱动（Flickable），fillHeight 无效；
               用页面可视高度兜底让左右栏撑满首屏，大窗不再出现底部死空间 */
            Layout.preferredHeight: Math.max(implicitHeight, root.height - 180)
            columnSpacing: 12
            rowSpacing: 12
            columns: root.wideMode ? 2 : 1

            // ---- 左侧内容 ----
        StackLayout {
            id: leftStack
            Layout.fillWidth: !root.wideMode || !root.isListSource
            Layout.preferredWidth: root.wideMode ? Math.max(300, parent.width * 0.38) : parent.width
            Layout.maximumWidth: root.isListSource && root.wideMode ? 480 : parent.width
            Layout.fillHeight: true
            currentIndex: root.currentSourceIndex

            // index 0: local — 本地文库
            TextSourceListPanel {
                id: localPanel
                title: qsTr("文章")
                icon: "ic_fluent_library_20_regular"
                sourceItems: root.localItems
                loading: root.currentSource === "local" && (appBridge ? appBridge.localArticleLoading : false)
                emptyText: qsTr("暂无本地文章")
                errorText: root.localListError
                onItemClicked: function(originalIndex) { root.selectListItem("local", originalIndex) }
                onRefreshRequested: {
                    root.localListError = ""
                    if (appBridge) appBridge.loadLocalArticles()
                }

                ToolButton {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    icon.name: "ic_fluent_add_20_regular"
                    flat: true
                    onClicked: {
                        if (Window.window && Window.window.navigationView)
                            Window.window.navigationView.push(Qt.resolvedUrl("UploadTextPage.qml"))
                    }
                    ToolTip { text: qsTr("导入文本"); visible: parent.hovered }
                }
            }

            // index 1: repos — 开源文库（按源/规则细分分组浏览）
            RepoEntriesPanel {
                entries: root.federatedEntries
                loading: root.currentSource === "repos" && (appBridge ? appBridge.federatedEntriesLoading : false)
                errorText: root.reposEntriesError
                selectedEntry: root.selectedItem
                // 源组头刷新动画：源级刷新不置列表级 loading，只驱动对应源组；
                // refreshingSources 为并发集合（多源同时刷新各播各的动画）
                refreshingSource: appBridge ? appBridge.refreshingFederatedSource : ""
                refreshingSources: appBridge ? appBridge.refreshingFederatedSources : []
                sourceStatuses: root.federatedSourceStatuses
                onEntryClicked: function(entry) {
                    root.selectedItem = entry
                    root.previewContent = entry.content || entry.preview || ""
                    root.checkProgress()
                }
                // 双击 = 选中 + 载入跟打（与右栏「载入跟打」同一路径与前置校验）
                onEntryActivated: function(entry) {
                    root.selectedItem = entry
                    root.previewContent = entry.content || entry.preview || ""
                    root.checkProgress()
                    Qt.callLater(function() {
                        if (root.readyForLoad && !root.federatedContentLoading)
                            root.loadSelectedItem()
                    })
                }
                // 总刷新 = 全部源强制换新；源组头刷新 = 该源（authority）换新
                onRefreshRequested: { if (appBridge) appBridge.refreshFederatedAll() }
                onRefreshSourceRequested: function(authority) { if (appBridge) appBridge.refreshFederatedSource(authority) }
                onAddRepoRequested: addRepoDialog.open()
                onSubscriptionsRequested: subscriptionsDialog.open()
                onSourceInfoRequested: function(authority) {
                    var entry = null
                    for (var i = 0; i < root.federatedEntries.length; i++) {
                        if ((root.federatedEntries[i]._authority || root.federatedEntries[i].authority || "") === authority) {
                            entry = root.federatedEntries[i]; break
                        }
                    }
                    sourceInfoDialog.authority = authority
                    sourceInfoDialog.sourceLabel = entry ? (entry._source_label || entry.source_label || authority) : authority
                    sourceInfoDialog.sourceType = entry ? (entry._source_type || "") : ""
                    sourceInfoDialog.repoId = entry ? (entry._repo_id || "") : ""
                    sourceInfoDialog.repoUrl = entry ? (entry._repo_url || "") : ""
                    sourceInfoDialog.open()
                }
                onManageRepoRequested: function(repoId, url) {
                    repoConfigDialog.repoId = repoId
                    repoConfigDialog.repoUrl = url
                    repoConfigDialog.open()
                }
            }

            // index 2: trainer — 练单器
            TextSourceListPanel {
                id: trainerPanel
                title: qsTr("词库")
                icon: "ic_fluent_apps_list_detail_20_regular"
                sourceItems: root.trainerItems
                loading: root.currentSource === "trainer" && (appBridge ? appBridge.trainerLoading : false)
                emptyText: qsTr("暂无练单器词库")
                errorText: root.trainerListError
                onItemClicked: function(originalIndex) { root.selectListItem("trainer", originalIndex) }
                onRefreshRequested: {
                    root.trainerListError = ""
                    if (appBridge) appBridge.loadTrainers()
                }
            }

            // index 3: wenlai — 晴发文
            WenlaiSourcePanel {
                id: wenlaiPanel
                onLoadRequested: {
                    wenlaiPanel.errorText = ""
                    root.navigateToTyping()
                    Qt.callLater(function() {
                        if (appBridge) appBridge.loadRandomWenlaiText()
                    })
                }
            }

            // index 4: ai — AI 推荐
            AiSourcePanel {
                id: aiPanel
                onLoadRequested: {
                    aiPanel.errorText = ""
                    root.navigateToTyping()
                    Qt.callLater(function() {
                        if (appBridge) appBridge.requestAiText()
                    })
                }
            }

            // index 5: custom — 自定义
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                Rectangle {
                    anchors.fill: parent
                    radius: 6
                    color: Theme.currentTheme.colors.cardColor
                    border.color: Theme.currentTheme.colors.cardBorderColor
                    border.width: 1
                }

                TextLoadPanel {
                    id: textLoadPanel
                    anchors.fill: parent
                    anchors.margins: 8
                }
            }
        }

            // ---- 右侧预览与设置 ----
            Frame {
                id: rightPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.isListSource
                radius: 6
                hoverable: false
                padding: 12

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        spacing: 8

                        IconWidget {
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            icon: "ic_fluent_open_20_regular"
                            color: Theme.currentTheme.colors.primaryColor
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: root.itemDisplayTitle()
                            elide: Text.ElideRight
                        }

                        // 来源专属操作（当前仅 local 有「重命名/删除」）
                        Row {
                            spacing: 4
                            visible: SrcBehav.capabilities[root.currentSource].supportsEdit && root.selectedItem !== null

                            ToolButton {
                                icon.name: "ic_fluent_rename_20_regular"
                                size: 16
                                flat: true
                                enabled: root.selectedItem && !root.selectedItem.isBundled
                                onClicked: renameDialog.open()
                                ToolTip { text: qsTr("重命名"); visible: parent.hovered }
                            }
                            ToolButton {
                                icon.name: "ic_fluent_delete_20_regular"
                                size: 16
                                flat: true
                                enabled: root.selectedItem && !root.selectedItem.isBundled
                                onClicked: deleteConfirmDialog.open()
                                ToolTip { text: qsTr("删除"); visible: parent.hovered }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    TextInfoCard {
                        id: textInfoCard
                        Layout.fillWidth: true
                        title: root.itemDisplayTitle()
                        textId: root.itemDisplayId()
                        charCount: root.itemDisplayCharCount()
                        content: root.itemDisplayContent()
                        // custom 来源靠字数校验，其余靠是否选中；supportsPreview==false 的来源永不展示
                        visible: SrcBehav.capabilities[root.currentSource].supportsPreview
                                && (root.currentSource === "custom"
                                    ? (textLoadPanel && textLoadPanel.contentText.length > 0)
                                    : root.selectedItem !== null)
                    }

                    SliceSettingsPanel {
                        id: sliceSettingsPanel
                        Layout.fillWidth: true
                        contentLength: root.itemDisplayCharCount()
                        sliceSize: 100
                        startSlice: 1
                        sliceModeChecked: root.sliceModeChecked
                        onSliceModeCheckedChanged: root.sliceModeChecked = sliceModeChecked
                    }

                    SliceCriteriaPanel {
                        id: sliceCriteriaPanel
                        Layout.fillWidth: true
                        visible: root.sliceModeChecked
                    }

                    Item { Layout.fillHeight: true }

                    Text {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        typography: Typography.Caption
                        color: root.errorMessage.length > 0 ? Theme.currentTheme.colors.systemCriticalColor : Theme.currentTheme.colors.textSecondaryColor
                        text: root.errorMessage.length > 0 ? root.errorMessage : root.statusMessage
                        elide: Text.ElideRight
                        visible: text.length > 0
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        spacing: 8

                        Item { Layout.fillWidth: true }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("刷新")
                            // 开源文库左栏自带「刷新全部」与源级刷新，右栏不再重复
                            visible: SrcBehav.capabilities[root.currentSource].supportsRefresh
                                     && root.currentSource !== "repos"
                            enabled: !root.currentSourceLoading()
                            onClicked: {
                                if (!appBridge) return
                                // 在哪个层级刷新哪个层级的源：
                                // repos 当前显示的列表即联邦聚合 → 全部源强制换新；
                                // 其余来源沿用各自列表加载
                                if (root.currentSource === "repos") appBridge.refreshFederatedAll()
                                else root.loadCurrentSource()
                            }
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("继续上次进度")
                            visible: SrcBehav.capabilities[root.currentSource].supportsProgress && root.canContinue()
                            enabled: root.canContinue()
                            onClicked: root.continueLastProgress()
                        }

                        BusyIndicator {
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            running: root.federatedContentLoading
                            visible: running
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("载入跟打")
                            highlighted: root.readyForLoad && !root.federatedContentLoading
                            enabled: root.readyForLoad && !root.federatedContentLoading
                            onClicked: root.loadSelectedItem()
                        }
                    }
                }
            }
        }
    }

    // ---- 对话框 ----
    // 订阅源配置弹窗（开源文库源组头「管理该源」入口）
    RepoConfigDialog {
        id: repoConfigDialog
    }

    // 源详情弹窗（类型/健康状态/刷新频率覆盖）
    SourceInfoDialog {
        id: sourceInfoDialog
        onManageRepoRequested: function(repoId, url) {
            repoConfigDialog.repoId = repoId
            repoConfigDialog.repoUrl = url
            repoConfigDialog.open()
        }
    }

    // 我的订阅：订阅级列表（含无条目组的订阅），每行进 RepoConfigDialog
    SubscriptionsDialog {
        id: subscriptionsDialog
        onManageRequested: function(repoId, url) {
            repoConfigDialog.repoId = repoId
            repoConfigDialog.repoUrl = url
            repoConfigDialog.open()
        }
        onAddRequested: addRepoDialog.open()
    }

    // 添加订阅（开源文库「添加订阅」入口）
    Dialog {
        id: addRepoDialog
        title: qsTr("添加订阅")
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string _error: ""
        property bool _awaitingAdd: false
        property var _preview: null
        property var _directoryRepos: []

        onOpened: {
            addRepoUrlField.text = ""
            addRepoDialog._error = ""
            addRepoDialog._preview = null
            addRepoDialog._directoryRepos = []
            addRepoUrlField.forceActiveFocus()
        }
        onAccepted: {
            var u = addRepoUrlField.text.trim()
            if (u.length > 0 && appBridge) {
                addRepoDialog._awaitingAdd = true
                appBridge.addRepo(u)
            }
        }

        // 添加失败（网络/校验）→ 弹窗内提示，不关闭
        Connections {
            target: appBridge
            function onReposLoadFailed(message) {
                addRepoDialog._awaitingAdd = false
                addRepoDialog._error = message
                addRepoDialog.open()
            }
            function onReposChanged(repos) {
                if (!addRepoDialog._awaitingAdd) return
                addRepoDialog._awaitingAdd = false
                root.statusMessage = qsTr("订阅添加成功")
                root._notifySuccess(qsTr("订阅添加成功"), 1800)
            }
            function onRepoManifestPreviewed(result) {
                root.repoManifestPreviewLoading = false
                if (result && result.error) {
                    addRepoDialog._error = result.error
                } else {
                    addRepoDialog._preview = result
                    if (result && result.type === "directory" && result.repositories)
                        addRepoDialog._directoryRepos = result.repositories
                }
            }
        }

        ColumnLayout {
            width: 420
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: qsTr("粘贴源仓库订阅 URL（ott-repo.json）：")
            }

            TextField {
                id: addRepoUrlField
                Layout.fillWidth: true
                placeholderText: "https://example.com/ott-repo.json"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: qsTr("预览")
                    flat: true
                    enabled: addRepoUrlField.text.trim().length > 0 && appBridge !== null
                    onClicked: {
                        addRepoDialog._error = ""
                        addRepoDialog._preview = null
                        addRepoDialog._directoryRepos = []
                        root.repoManifestPreviewLoading = true
                        appBridge.previewRepoManifest(addRepoUrlField.text.trim())
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: addRepoDialog._preview !== null
                    text: addRepoDialog._preview
                          ? (addRepoDialog._preview.name + (addRepoDialog._preview.description ? " — " + addRepoDialog._preview.description : ""))
                          : ""
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    elide: Text.ElideRight
                }
            }

            // 目录 manifest：列出可添加的仓库引用（不自动订阅）
            ColumnLayout {
                visible: addRepoDialog._directoryRepos.length > 0
                Layout.fillWidth: true
                spacing: 4

                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("该地址是一个目录，选择要添加的仓库：")
                }

                Repeater {
                    model: addRepoDialog._directoryRepos
                    delegate: Button {
                        Layout.fillWidth: true
                        text: modelData.label || modelData.url
                        flat: true
                        onClicked: {
                            if (appBridge) appBridge.addRepo(modelData.url)
                            addRepoDialog.close()
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                color: Theme.currentTheme.colors.systemCriticalColor
                text: addRepoDialog._error
                wrapMode: Text.Wrap
                visible: text.length > 0
            }
        }
    }

    Dialog {
        id: deleteConfirmDialog
        title: qsTr("确认删除")
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        Text {
            text: qsTr("确定要删除文章「%1」吗？此操作不可撤销。").arg(SrcBehav.articleTitle(root.selectedItem))
        }

        onAccepted: {
            var id = SrcBehav.articleId(root.selectedItem)
            if (appBridge && id) appBridge.deleteLocalArticle(id)
        }
    }

    Dialog {
        id: renameDialog
        title: qsTr("重命名")
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        RowLayout {
            Layout.fillWidth: true
            Text { text: qsTr("新名称：") }
            TextField {
                id: renameTextField
                Layout.fillWidth: true
                selectByMouse: true
            }
        }

        onOpened: {
            renameTextField.text = SrcBehav.articleTitle(root.selectedItem)
            renameTextField.selectAll()
            renameTextField.forceActiveFocus()
        }

        onAccepted: {
            var newName = renameTextField.text.trim()
            var id = SrcBehav.articleId(root.selectedItem)
            if (newName && appBridge && id) appBridge.renameLocalArticle(id, newName)
        }
    }

    SliceProgressRestoreDialog {
        id: progressRestoreDialog
        property string _source: ""
        property string _restoreId: ""
        property string _restoreTitle: ""

        onRestoreAccepted: {
            if (_source === "" || _source === "custom") {
                var text = textLoadPanel.contentText
                var rp = appBridge.applySliceProgressRestore(appBridge.getProgressKey("custom_text", text), true, textLoadPanel.selectedSourceLabel || "")
                root.startCustomTyping(rp)
                return
            }
            appBridge.prepareSliceProgressRestore(appBridge.getProgressKey(root.progressKeyType(), _restoreId), _restoreTitle)
            var settings = JSON.parse(appBridge.getRestoredSliceSettings())
            root.startTypingFromRequest(root.buildLaunchRequest(), settings)
        }

        onStartFresh: {
            if (_source === "" || _source === "custom") {
                appBridge.applySliceProgressRestore(appBridge.getProgressKey("custom_text", textLoadPanel.contentText), false, textLoadPanel.selectedSourceLabel || "")
                root.startCustomTyping()
                return
            }
            appBridge.applySliceProgressRestore(appBridge.getProgressKey(root.progressKeyType(), _restoreId), false, _restoreTitle)
            root.loadSelectedItem()
        }
    }

    // ---- AppBridge 信号 ----
    Connections {
        target: appBridge
        enabled: root.active

        function onLocalArticlesLoaded(articles) {
            if (root.active && root.currentSource === "local") {
                root._syncToCurrentList(articles)
                root.errorMessage = ""
                root.localListError = ""
            }
        }
        function onLocalArticlesLoadFailed(message) {
            if (root.active && root.currentSource === "local") {
                root.errorMessage = message
                root.statusMessage = ""
                root.localListError = message
            }
        }
        function onTrainersLoaded(trainers) {
            if (root.active && root.currentSource === "trainer") {
                // 必须走统一整形：原样塞 bridge 原始数据时，列表项没有
                // title/subtitle/raw 三件套——ListModel.append 遇到 undefined
                // 成员会警告且不建 role，导致后续 itemClicked 取到的 raw 为空，
                // 词库点了没反应（实测切到练单器即刷 17 条 warning）。
                root._syncToCurrentList(trainers)
                root.trainerListError = ""
            }
        }
        function onTrainersLoadFailed(message) {
            if (root.active && root.currentSource === "trainer") {
                root.trainerItems = []
                root.trainerListError = message
            }
        }
        function onLocalArticleSegmentLoaded(segment) {
            if (root.active) {
                var title = segment && segment.title ? segment.title : SrcBehav.articleTitle(root.selectedItem)
                root.statusMessage = qsTr("已载入：%1").arg(title)
                root.errorMessage = ""
            }
        }
        function onLocalArticleSegmentLoadFailed(message) {
            if (root.active) root.errorMessage = message
        }
        function onLocalArticlePreviewLoaded(content) {
            if (!root.active || root.currentSource !== "local") return
            root.previewContent = content || ""
            root.checkProgress()
        }
        function onTrainerPreviewLoaded(content) {
            if (!root.active || root.currentSource !== "trainer") return
            root.previewContent = content || ""
            root.checkProgress()
        }
        function onLocalArticleDeleted(success, message) {
            if (root.active) {
                if (success) { root.statusMessage = message; root.errorMessage = ""; appBridge.loadLocalArticles() }
                else root.errorMessage = message
            }
        }
        function onLocalArticleRenamed(success, message) {
            if (root.active) {
                if (success) { root.statusMessage = message; root.errorMessage = ""; appBridge.loadLocalArticles() }
                else root.errorMessage = message
            }
        }
        function onTrainerSegmentLoaded(segment) {
            if (root.active) {
                var title = segment && segment.title ? segment.title : SrcBehav.trainerTitle(root.selectedItem)
                root.statusMessage = qsTr("已载入：%1").arg(title)
                root.errorMessage = ""
            }
        }
        function onTrainerSegmentLoadFailed(message) {
            if (root.active) root.errorMessage = message
        }
    }

    // ---- 联邦跨页面信号（不依赖 root.active）----
    // 联邦条目载文后 hub 可能已被 push 到 TypingPage，root.active 为 false，
    // 若留在上方 enabled: root.active 的 Connections 中，textLoaded 落地信号会被
    // 守卫丢弃，载入跟打按钮的 busy 状态无法清除。此处独立 Connections 常驻处理。
    Connections {
        target: appBridge

        function onTextLoaded(text, textId, sourceLabel) {
            /* 联邦条目载文完成（segmented/inline 均直发 textLoaded），清除载文 busy 状态 */
            federatedLoadTimeoutTimer.stop()
            root.federatedContentLoading = false
        }
        function onTextLoadFailed(message) {
            /* 联邦载文失败：清除 busy 状态 */
            if (root.federatedContentLoading) {
                federatedLoadTimeoutTimer.stop()
                root.federatedContentLoading = false
                root.errorMessage = message
                root.statusMessage = ""
            }
        }
        function onRegistryFederatedEntriesLoadingChanged() {
            if (appBridge && appBridge.federatedEntriesLoading) {
                root.statusMessage = qsTr("正在加载条目…")
            }
        }
        // 即时源失败回流：载文落在 TypingPage，失败原因要留存在来源面板上，
        // 用户回到 hub 时能看到（再次发起时由面板自行清空）。
        function onWenlaiLoadFailed(message) {
            wenlaiPanel.errorText = message
        }
        function onAiTextFailed(message) {
            aiPanel.errorText = message
        }
        function onRegistryFederatedEntriesLoadFailed(message) {
            root.reposEntriesError = message
            root.statusMessage = ""
            federatedLoadTimeoutTimer.stop()
            root.federatedContentLoading = false
        }
        function onFederatedSourceStatusChanged(authority, status) {
            /* 源级刷新结果：只更新该源组健康状态，绝不写 reposEntriesError
               （否则单源失败会用错误页盖掉整个开源文库列表） */
            var next = {}
            for (var k in root.federatedSourceStatuses) next[k] = root.federatedSourceStatuses[k]
            next[authority] = status
            root.federatedSourceStatuses = next
            if (root.currentSource === "repos" && status && status.state === "failed") {
                root.statusMessage = qsTr("源刷新失败，正在显示缓存快照：%1").arg(authority)
            }
        }
        function onRegistryFederatedEntriesLoaded(entries) {
            /* 同步快照显示 + 后台 revalidate 完成都走这里。数据总是更新
               （保持最新存储），状态消息仅在当前处于开源文库时写入，
               避免后台刷新结果覆盖其他 tab 的状态消息 */
            root.federatedEntries = entries || []
            root.reposEntriesError = ""
            if (root.currentSource === "repos") {
                var result = SrcBehav.syncItems("repos", root.federatedEntries)
                root.statusMessage = result.statusMessage
            }
        }
    }
}
