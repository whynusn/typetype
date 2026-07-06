import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"
import "../components"

/**
 * 统一载文中心。
 *
 * 将极速杯、本地文库、开源文库、练单器、自定义 5 种来源收敛到单一页面。
 * 顶部为 Segmented 来源切换，左侧为对应列表/输入，右侧为统一的预览 + 切片设置 + 操作按钮。
 */
FluentPage {
    id: root
    title: qsTr("载文")
    horizontalPadding: 20
    wrapperWidth: 1200

    property bool active: false
    property string initialSource: ""
    property string currentSource: initialSource || "jisubei"

    // ---- 来源定义 ----
    readonly property var sourceKeys: ["jisubei", "local", "registry", "trainer", "custom"]
    readonly property var sourceLabels: [
        qsTr("极速杯"),
        qsTr("本地文库"),
        qsTr("开源文库"),
        qsTr("练单器"),
        qsTr("自定义")
    ]
    readonly property var sourceIcons: [
        "ic_fluent_document_text_20_regular",
        "ic_fluent_library_20_regular",
        "ic_fluent_text_bullet_list_20_regular",
        "ic_fluent_apps_list_detail_20_regular",
        "ic_fluent_edit_20_regular"
    ]

    readonly property int currentSourceIndex: sourceKeys.indexOf(currentSource)
    readonly property bool isListSource: currentSource !== "custom"
    readonly property bool isRegistry: currentSource === "registry"

    // ---- 响应式断点 ----
    readonly property bool wideMode: width >= 840

    // ---- 列表数据 ----
    property var jisubeiItems: []
    property var localItems: []
    property var registryItems: []
    property var trainerItems: []

    // ---- 当前选中项 ----
    property var selectedItem: null
    property string previewContent: ""
    property int serverTextId: 0
    property string statusMessage: ""
    property string errorMessage: ""
    property bool sliceModeChecked: true
    property bool hasProgress: false
    property bool catalogLoading: false  // 开源文库目录加载状态
    property bool registryLoading: false  // 开源文库单篇加载状态

    // ---- 初始化 / 激活 ----
    onActiveChanged: {
        if (active) {
            if (initialSource) {
                currentSource = initialSource
                initialSource = ""
            }
            loadCurrentSource()
            loadSlicePrefs()
        }
    }

    onCurrentSourceChanged: {
        selectedItem = null
        previewContent = ""
        serverTextId = 0
        errorMessage = ""
        statusMessage = ""
        registryLoading = false
        hasProgress = false
        if (active) loadCurrentSource()
    }

    function loadCurrentSource() {
        if (!appBridge) return
        switch (currentSource) {
        case "jisubei":
            statusMessage = qsTr("正在加载极速杯文本列表...")
            appBridge.loadTextList("jisubei")
            break
        case "local":
            statusMessage = qsTr("正在扫描本地文库...")
            appBridge.loadLocalArticles()
            break
        case "registry":
            statusMessage = qsTr("正在加载开源文库目录...")
            appBridge.loadCatalog()
            break
        case "trainer":
            statusMessage = qsTr("正在扫描练单器词库...")
            appBridge.loadTrainers()
            break
        case "custom":
            statusMessage = qsTr("请输入或粘贴文本")
            if (textLoadPanel) textLoadPanel.onCatalogLoaded(appBridge ? appBridge.textSourceOptions : [])
            break
        }
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

    // ---- 列表项工具函数 ----
    function textTitle(item) { return item ? (item.title || item.name || qsTr("未命名文本")) : qsTr("未选择文本") }
    function textCharCount(item) { return item ? (item.charCount || item.char_count || 0) : 0 }

    function articleId(article) {
        if (!article) return ""
        return article.articleId !== undefined ? article.articleId
             : article.article_id !== undefined ? article.article_id
             : article.id !== undefined ? article.id
             : article.client_id !== undefined ? article.client_id : ""
    }
    function articleTitle(article) { return article ? (article.title || article.name || article.filename || qsTr("未命名文章")) : qsTr("未选择文章") }
    function articleCharCount(article) { return article ? (article.charCount || article.char_count || article.contentLength || article.content_length || article.length || 0) : 0 }

    function trainerId(item) { return item ? (item.trainerId || item.trainer_id || item.id || "") : "" }
    function trainerTitle(item) { return item ? (item.title || item.name || trainerId(item) || qsTr("未命名词库")) : qsTr("未选择词库") }
    function trainerEntryCount(item) { return item ? (item.entryCount || item.entry_count || item.count || 0) : 0 }

    function entryLabel(entry) { return entry ? (entry.label || entry.sourceKey || "") : qsTr("未选择文本") }
    function entrySourceKey(entry) { return entry ? (entry.sourceKey || "") : "" }
    function entryCharCount(entry) {
        if (!entry) return 0
        return previewContent.length > 0 ? previewContent.length : (entry.charCount || 0)
    }

    function syncJisuBei(texts) {
        var arr = []
        if (texts) {
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i]
                arr.push({ title: t.title || "", subtitle: qsTr("%1 字").arg(t.charCount !== undefined ? t.charCount : 0), raw: t })
            }
        }
        jisubeiItems = arr
        statusMessage = arr.length > 0 ? qsTr("已加载 %1 篇文本").arg(arr.length) : qsTr("未找到文本")
    }

    function syncLocal(articles) {
        var arr = []
        if (articles) {
            for (var i = 0; i < articles.length; i++) {
                var a = articles[i]
                arr.push({ title: articleTitle(a), subtitle: qsTr("%1 字").arg(articleCharCount(a)), raw: a })
            }
        }
        localItems = arr
        statusMessage = arr.length > 0 ? qsTr("已加载 %1 篇本地文章").arg(arr.length) : qsTr("未找到本地文章")
    }

    function syncRegistry(catalog) {
        var arr = []
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                var c = catalog[i]
                var desc = c.description || ""
                if (c.charCount > 0) desc += (desc ? " • " : "") + c.charCount + qsTr("字")
                arr.push({ title: c.label || c.key || "", subtitle: desc, raw: { sourceKey: c.key, label: c.label || c.key, charCount: c.charCount || 0, description: c.description || "" } })
            }
        }
        registryItems = arr
        statusMessage = arr.length > 0 ? qsTr("已加载 %1 篇开源文库文本").arg(arr.length) : qsTr("暂无开源文库文本")
    }

    function syncTrainer(items) {
        var arr = []
        if (items) {
            for (var i = 0; i < items.length; i++) {
                var it = items[i]
                arr.push({ title: trainerTitle(it), subtitle: qsTr("%1 项").arg(trainerEntryCount(it)), raw: it })
            }
        }
        trainerItems = arr
        statusMessage = arr.length > 0 ? qsTr("已加载 %1 个词库").arg(arr.length) : qsTr("未找到练单器词库")
    }

    // ---- 选择事件 ----
    function selectListItem(source, originalIndex) {
        var items = []
        if (source === "jisubei") items = jisubeiItems
        else if (source === "local") items = localItems
        else if (source === "registry") items = registryItems
        else if (source === "trainer") items = trainerItems
        if (originalIndex < 0 || originalIndex >= items.length) {
            selectedItem = null
            return
        }
        selectedItem = items[originalIndex].raw
        previewContent = ""
        serverTextId = 0
        errorMessage = ""
        statusMessage = qsTr("已选择：%1").arg(itemDisplayTitle())
        registryLoading = false
        hasProgress = false

        if (source === "jisubei" && selectedItem && selectedItem.id && appBridge) {
            appBridge.getTextContentById(selectedItem.id)
        } else if (source === "registry") {
            // 开源文库内容在点击"载入跟打"时加载
            checkProgress()
        } else {
            checkProgress()
        }
    }

    // ---- 信息卡展示 ----
    function itemDisplayTitle() {
        if (!selectedItem) {
            if (currentSource === "custom") return textLoadPanel ? textLoadPanel.selectedSourceLabel || qsTr("自定义文本") : qsTr("自定义文本")
            return qsTr("未选择文本")
        }
        if (currentSource === "jisubei") return textTitle(selectedItem)
        if (currentSource === "local") return articleTitle(selectedItem)
        if (currentSource === "registry") return entryLabel(selectedItem)
        if (currentSource === "trainer") return trainerTitle(selectedItem)
        return qsTr("未选择文本")
    }

    function itemDisplayId() {
        if (!selectedItem) return null
        if (currentSource === "jisubei") return serverTextId
        if (currentSource === "local") return articleId(selectedItem)
        if (currentSource === "trainer") return trainerId(selectedItem)
        return null
    }

    function itemDisplayCharCount() {
        if (currentSource === "custom") return textLoadPanel ? textLoadPanel.contentLength : 0
        if (!selectedItem) return 0
        if (currentSource === "jisubei") return previewContent.length > 0 ? previewContent.length : textCharCount(selectedItem)
        if (currentSource === "local") return articleCharCount(selectedItem)
        if (currentSource === "registry") return entryCharCount(selectedItem)
        if (currentSource === "trainer") return trainerEntryCount(selectedItem)
        return 0
    }

    function itemDisplayContent() {
        if (currentSource === "custom") return textLoadPanel ? textLoadPanel.contentText.substring(0, 200) : ""
        if (currentSource === "jisubei") return previewContent
        if (currentSource === "registry") return previewContent.substring(0, 200)
        return ""
    }

    // ---- 进度 ----
    function progressKeyType() {
        if (currentSource === "local") return "local_article"
        if (currentSource === "trainer") return "trainer"
        return "custom_text"
    }

    function progressIdentifier() {
        if (currentSource === "local") return articleId(selectedItem)
        if (currentSource === "trainer") return trainerId(selectedItem)
        if (currentSource === "jisubei") return previewContent
        return textLoadPanel ? textLoadPanel.contentText : ""
    }

    function checkProgress() {
        if (!appBridge || !selectedItem || currentSource === "registry") {
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

    function appBridgeLoading() {
        if (!appBridge) return false
        return appBridge.textListLoading || appBridge.localArticleLoading || appBridge.trainerLoading || registryLoading
    }

    function loadSelectedItem(rp) {
        if (!appBridge) return
        if (currentSource === "custom") { startCustomTyping(rp); return }
        if (currentSource === "registry") {
            if (!selectedItem) { errorMessage = qsTr("请选择一个文本"); return }
            registryLoading = true
            appBridge.loadLibraryText(entrySourceKey(selectedItem))
            statusMessage = qsTr("正在从开源文库加载...")
            return
        }
        if (!selectedItem) { errorMessage = qsTr("请选择一个项目"); return }

        appBridge.clearPendingRestore()
        var fullText = !sliceModeChecked
        var size = sliceSettingsPanel.sliceSize
        var index = Math.max(1, Math.min(sliceSettingsPanel.startSlice, sliceSettingsPanel.totalSlices))

        if (currentSource === "jisubei") {
            var text = previewContent
            if (!text) { errorMessage = qsTr("文本内容尚未加载"); return }
            if (fullText) { size = text.length; index = 1 }
            setupSliceCriteria(rp)
            navigateToTyping()
            var title = itemDisplayTitle()
            Qt.callLater(function() {
                if (fullText) appBridge.loadFullText(text, "jisubei", title, serverTextId)
                else appBridge.setupSliceMode(text, size, index,
                    sliceCriteriaPanel.keyStrokeMinValue, sliceCriteriaPanel.speedMinValue,
                    sliceCriteriaPanel.accuracyMinValue, sliceCriteriaPanel.passCountMinValue,
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.onFailActionValue : "none",
                    sliceCriteriaPanel.autoDecreaseEnabled, sliceCriteriaPanel.keyStrokeDecreaseValue,
                    sliceCriteriaPanel.speedDecreaseValue, sliceCriteriaPanel.accuracyDecreaseValue,
                    rp ? JSON.stringify(rp) : "", title)
            })
        } else if (currentSource === "local") {
            var id = articleId(selectedItem)
            if (!id) { errorMessage = qsTr("文章缺少 ID"); return }
            if (fullText) { size = articleCharCount(selectedItem); index = 1 }
            setupSliceCriteria(rp)
            navigateToTyping()
            Qt.callLater(function() { appBridge.loadLocalArticleSegment(id, index, size) })
        } else if (currentSource === "trainer") {
            var tid = trainerId(selectedItem)
            if (!tid) { errorMessage = qsTr("词库缺少 ID"); return }
            if (fullText) { size = trainerEntryCount(selectedItem); index = 1 }
            setupSliceCriteria(rp)
            navigateToTyping()
            Qt.callLater(function() { appBridge.loadTrainerSegment(tid, index, size) })
        }
    }

    function startCustomTyping(rp) {
        if (!appBridge) return
        var text = textLoadPanel.contentText
        if (!text) { errorMessage = qsTr("请输入文本"); return }
        if (!rp) appBridge.clearPendingRestore()

        var s = rp || {}
        var fullText = !textLoadPanel.sliceModeChecked
        var sliceSize = s.slice_size > 0 ? s.slice_size : textLoadPanel.sliceSize
        var startSlice = s.current_slice > 0 ? s.current_slice : textLoadPanel.startSlice
        if (fullText) { sliceSize = text.length; startSlice = 1 }

        setupSliceCriteria(rp)
        navigateToTyping()
        var title = textLoadPanel.selectedSourceLabel || qsTr("自定义文本")
        var sourceKey = textLoadPanel.selectedSourceKey || "custom"
        Qt.callLater(function() {
            if (fullText) appBridge.loadFullText(text, sourceKey, title)
            else appBridge.setupSliceMode(text, sliceSize, startSlice,
                sliceCriteriaPanel.keyStrokeMinValue, sliceCriteriaPanel.speedMinValue,
                sliceCriteriaPanel.accuracyMinValue, sliceCriteriaPanel.passCountMinValue,
                sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.onFailActionValue : "none",
                sliceCriteriaPanel.autoDecreaseEnabled, sliceCriteriaPanel.keyStrokeDecreaseValue,
                sliceCriteriaPanel.speedDecreaseValue, sliceCriteriaPanel.accuracyDecreaseValue,
                rp ? JSON.stringify(rp) : "", title)
        })
    }

    function canLoad() {
        if (!appBridge) return false
        if (currentSource === "custom") return textLoadPanel && textLoadPanel.contentText.length > 0
        if (currentSource === "registry") return selectedItem !== null && !registryLoading
        if (currentSource === "jisubei") return selectedItem !== null && previewContent.length > 0
        return selectedItem !== null
    }

    function canContinue() {
        return hasProgress && canLoad()
    }

    // ===================================================================
    // UI
    // ===================================================================

    ColumnLayout {
        id: container
        width: parent.width
        spacing: 16

        // ---- 顶部来源切换 (Segmented) ----
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            radius: 8
            hoverable: false
            color: Theme.currentTheme.colors.subtleColor

            Segmented {
                id: sourceSelector
                anchors.fill: parent
                currentIndex: root.currentSourceIndex
                onCurrentIndexChanged: {
                    if (currentIndex !== -1 && currentIndex !== root.currentSourceIndex) {
                        root.currentSource = root.sourceKeys[currentIndex]
                    }
                }

                Repeater {
                    model: root.sourceKeys.length
                    SegmentedItem {
                        text: root.sourceLabels[index]
                        icon.name: root.sourceIcons[index]
                    }
                }
            }
        }

        // ---- 主体 ----
        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columnSpacing: 12
            rowSpacing: 12
            columns: root.wideMode ? 2 : 1

            // ---- 左侧内容 ----
            StackLayout {
                id: leftStack
                Layout.fillWidth: !root.wideMode
                Layout.preferredWidth: root.wideMode ? Math.max(300, parent.width * 0.38) : parent.width
                Layout.maximumWidth: root.wideMode ? 480 : parent.width
                Layout.fillHeight: true
                currentIndex: root.currentSourceIndex

                TextSourceListPanel {
                    title: qsTr("文本列表")
                    icon: "ic_fluent_document_text_20_regular"
                    sourceItems: root.jisubeiItems
                    loading: root.currentSource === "jisubei" && (appBridge ? appBridge.textListLoading : false)
                    emptyText: qsTr("暂无文本")
                    onItemClicked: { root.selectListItem("jisubei", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.loadTextList("jisubei") }
                }

                TextSourceListPanel {
                    title: qsTr("文章")
                    icon: "ic_fluent_document_text_20_regular"
                    sourceItems: root.localItems
                    loading: root.currentSource === "local" && (appBridge ? appBridge.localArticleLoading : false)
                    emptyText: qsTr("暂无本地文章")
                    onItemClicked: { root.selectListItem("local", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.loadLocalArticles() }

                    ToolButton {
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        icon.name: "ic_fluent_add_20_regular"
                        flat: true
                        onClicked: {
                            if (Window.window && Window.window.navigationView)
                                Window.window.navigationView.push(Qt.resolvedUrl("UploadTextPage.qml"))
                        }
                        ToolTip { text: qsTr("上传文本"); visible: parent.hovered }
                    }
                }

                TextSourceListPanel {
                    title: qsTr("文本列表")
                    icon: "ic_fluent_document_text_20_regular"
                    sourceItems: root.registryItems
                    loading: root.currentSource === "registry" && (appBridge ? appBridge.catalogLoading : false)
                    emptyText: qsTr("暂无文本")
                    onItemClicked: { root.selectListItem("registry", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.refreshCatalog() }
                }

                TextSourceListPanel {
                    title: qsTr("词库")
                    icon: "ic_fluent_text_bullet_list_square_20_regular"
                    sourceItems: root.trainerItems
                    loading: root.currentSource === "trainer" && (appBridge ? appBridge.trainerLoading : false)
                    emptyText: qsTr("暂无练单器词库")
                    onItemClicked: { root.selectListItem("trainer", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.loadTrainers() }
                }

                Item {
                    TextLoadPanel {
                        id: textLoadPanel
                        anchors.fill: parent
                        compactMode: false
                        hubMode: true
                        textSourceOptions: appBridge ? appBridge.textSourceOptions : []
                        defaultTextSourceKey: appBridge ? appBridge.defaultTextSourceKey : ""
                    }
                }
            }

            // ---- 右侧预览与设置 ----
            Frame {
                id: rightPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
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

                        // 本地文章操作按钮
                        Row {
                            spacing: 4
                            visible: root.currentSource === "local" && root.selectedItem !== null

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
                        visible: root.currentSource === "custom" ? (textLoadPanel && textLoadPanel.contentText.length > 0)
                                                                  : root.selectedItem !== null
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
                            visible: root.currentSource !== "custom"
                            enabled: !appBridgeLoading()
                            onClicked: root.loadCurrentSource()
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("继续上次进度")
                            visible: root.canContinue() && root.currentSource !== "registry"
                            enabled: root.canContinue()
                            onClicked: root.continueLastProgress()
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("载入跟打")
                            highlighted: true
                            enabled: root.canLoad() && !sliceCriteriaPanel.validationMessage && !appBridgeLoading()
                            onClicked: root.loadSelectedItem()
                        }
                    }
                }
            }
        }
    }

    // ---- 对话框 ----
    Dialog {
        id: deleteConfirmDialog
        title: qsTr("确认删除")
        modal: true
        anchors.centerIn: QQC.Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel

        Text {
            text: qsTr("确定要删除文章「%1」吗？此操作不可撤销。").arg(root.articleTitle(root.selectedItem))
        }

        onAccepted: {
            var id = root.articleId(root.selectedItem)
            if (appBridge && id) appBridge.deleteLocalArticle(id)
        }
    }

    Dialog {
        id: renameDialog
        title: qsTr("重命名")
        modal: true
        anchors.centerIn: QQC.Overlay.overlay
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
            renameTextField.text = root.articleTitle(root.selectedItem)
            renameTextField.selectAll()
            renameTextField.forceActiveFocus()
        }

        onAccepted: {
            var newName = renameTextField.text.trim()
            var id = root.articleId(root.selectedItem)
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
                textLoadPanel.startSlice = 1
                root.startCustomTyping(rp)
                return
            }
            appBridge.prepareSliceProgressRestore(appBridge.getProgressKey(root.progressKeyType(), _restoreId), _restoreTitle)
            var settings = JSON.parse(appBridge.getRestoredSliceSettings())
            SliceHelpers.startWithCriteria(
                appBridge, Window.window ? Window.window.navigationView : null,
                sliceSettingsPanel, sliceCriteriaPanel, settings,
                function(size) {
                    if (_source === "jisubei") {
                        var text = root.previewContent
                        var title = root.itemDisplayTitle()
                        var fullText = !sliceSettingsPanel.sliceModeChecked
                        if (fullText) { size = text.length }
                        if (fullText) appBridge.loadFullText(text, "jisubei", title, root.serverTextId)
                        else appBridge.setupSliceMode(text, size, 1,
                            sliceCriteriaPanel.keyStrokeMinValue, sliceCriteriaPanel.speedMinValue,
                            sliceCriteriaPanel.accuracyMinValue, sliceCriteriaPanel.passCountMinValue,
                            sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.onFailActionValue : "none",
                            sliceCriteriaPanel.autoDecreaseEnabled, sliceCriteriaPanel.keyStrokeDecreaseValue,
                            sliceCriteriaPanel.speedDecreaseValue, sliceCriteriaPanel.accuracyDecreaseValue,
                            "", title)
                    } else if (_source === "local") {
                        appBridge.loadLocalArticleSegment(root.articleId(root.selectedItem), 1, size)
                    } else if (_source === "trainer") {
                        appBridge.loadTrainerSegment(root.trainerId(root.selectedItem), 1, size)
                    }
                }
            )
        }

        onStartFresh: {
            if (_source === "" || _source === "custom") {
                appBridge.applySliceProgressRestore(appBridge.getProgressKey("custom_text", textLoadPanel.contentText), false, textLoadPanel.selectedSourceLabel || "")
                textLoadPanel.startSlice = 1
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

        function onTextListLoaded(texts) {
            if (root.currentSource === "jisubei") {
                root.syncJisuBei(texts)
                root.errorMessage = ""
            }
        }
        function onTextListLoadFailed(message) {
            if (root.currentSource === "jisubei") { root.errorMessage = message; root.statusMessage = "" }
        }
        function onTextContentLoaded(textId, content, title) {
            if (!root.active) return
            if (root.currentSource === "jisubei") {
                root.serverTextId = textId || 0
                root.previewContent = content || ""
                root.statusMessage = qsTr("已载入：%1").arg(title || root.itemDisplayTitle())
                root.errorMessage = ""
                root.checkProgress()
            } else if (root.currentSource === "registry" && root.registryLoading) {
                root.registryLoading = false
                root.previewContent = content || ""
                var sourceKey = root.entrySourceKey(root.selectedItem)
                var displayTitle = title || root.itemDisplayTitle()
                appBridge.setSliceCriteria(
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.keyStrokeMinValue : 0,
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.speedMinValue : 0,
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.accuracyMinValue : 0,
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.passCountMinValue : 1,
                    sliceCriteriaPanel.conditionChecked ? sliceCriteriaPanel.onFailActionValue : "none",
                    sliceCriteriaPanel.advanceModeValue,
                    sliceSettingsPanel.fullShuffleChecked,
                    sliceCriteriaPanel.autoDecreaseEnabled,
                    sliceCriteriaPanel.keyStrokeDecreaseValue,
                    sliceCriteriaPanel.speedDecreaseValue,
                    sliceCriteriaPanel.accuracyDecreaseValue
                )
                root.navigateToTyping()
                Qt.callLater(function() {
                    if (appBridge && content) appBridge.loadFullText(content, sourceKey, displayTitle, textId)
                })
            }
        }
        function onTextLoadFailed(message) {
            if (root.currentSource === "registry" && root.registryLoading) {
                root.registryLoading = false
                root.errorMessage = message
            }
        }
        function onCatalogLoaded(catalog) {
            if (root.active) {
                root.syncRegistry(catalog)
                root.errorMessage = ""
                if (textLoadPanel) textLoadPanel.onCatalogLoaded(catalog)
            }
        }
        function onCatalogLoadFailed(message) {
            if (root.active && root.currentSource === "registry") {
                root.catalogLoading = true
                root.errorMessage = message
                root.statusMessage = ""
            }
        }
        function onLocalArticlesLoaded(articles) {
            if (root.active && root.currentSource === "local") {
                root.syncLocal(articles)
                root.errorMessage = ""
            }
        }
        function onLocalArticlesLoadFailed(message) {
            if (root.active && root.currentSource === "local") { root.errorMessage = message; root.statusMessage = "" }
        }
        function onLocalArticleSegmentLoaded(segment) {
            if (root.active) {
                var title = segment && segment.title ? segment.title : root.articleTitle(root.selectedItem)
                root.statusMessage = qsTr("已载入：%1").arg(title)
                root.errorMessage = ""
            }
        }
        function onLocalArticleSegmentLoadFailed(message) {
            if (root.active) root.errorMessage = message
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
        function onTrainersLoaded(items) {
            if (root.active && root.currentSource === "trainer") {
                root.syncTrainer(items)
                root.errorMessage = ""
            }
        }
        function onTrainersLoadFailed(message) {
            if (root.active && root.currentSource === "trainer") { root.errorMessage = message; root.statusMessage = "" }
        }
        function onTrainerSegmentLoaded(segment) {
            if (root.active) {
                var title = segment && segment.title ? segment.title : root.trainerTitle(root.selectedItem)
                root.statusMessage = qsTr("已载入：%1").arg(title)
                root.errorMessage = ""
            }
        }
        function onTrainerSegmentLoadFailed(message) {
            if (root.active) root.errorMessage = message
        }
    }
}
