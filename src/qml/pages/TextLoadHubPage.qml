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
        // 注册表分派当前来源的列表加载（bridge 调用 + 状态消息）
        var msg = SrcBehav.loadList(appBridge, currentSource)
        if (msg) statusMessage = msg
        if (currentSource === "custom" && textLoadPanel)
            textLoadPanel.onCatalogLoaded(appBridge ? appBridge.textSourceOptions : [])
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
        serverTextId = 0
        errorMessage = ""
        statusMessage = qsTr("已选择：%1").arg(itemDisplayTitle())
        if (source === "registry") registryLoading = false  // 仅 registry 使用
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
        return SrcBehav.cardIdText(currentSource, selectedItem, serverTextId) ? serverTextId : null
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
                                         textLoadPanel ? textLoadPanel.contentText : "",
                                         serverTextId).key
    }
    function progressIdentifier() {
        return SrcBehav.progressKeyAndId(currentSource, selectedItem, previewContent,
                                         textLoadPanel ? textLoadPanel.contentText : "",
                                         serverTextId).identifier
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

    // 注册 custom 来源的字数 getter（供 canLoadImpl 在 JS 中判读）
    Component.onCompleted: {
        SrcBehav.registerCustomTextLenGetter(function () {
            return textLoadPanel ? textLoadPanel.contentText.trim().length : 0
        })
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

    // 当前来源的加载状态（来源感知，不再把其它来源的 loading 混进来）
    function currentSourceLoading() {
        return SrcBehav.isLoading(currentSource, appBridge, root)
    }

    // 统一的「就绪」表达：当前来源已加载完成 + 已满足 canLoad 前置条件
    // 供「载入跟打」按钮的 enabled / highlighted 绑定，避免按钮颜色受无关来源 API 牵制
    property bool readyForLoad: canLoad() && !currentSourceLoading() && !sliceCriteriaPanel.validationMessage

    function loadSelectedItem(rp) {
        if (!appBridge) return
        if (currentSource === "custom") { startCustomTyping(rp); return }
        if (currentSource === "registry") {
            if (!selectedItem) { errorMessage = qsTr("请选择一个文本"); return }
            registryLoading = true
            appBridge.loadLibraryText(SrcBehav.entrySourceKey(selectedItem))
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
            var id = SrcBehav.articleId(selectedItem)
            if (!id) { errorMessage = qsTr("文章缺少 ID"); return }
            if (fullText) { size = SrcBehav.articleCharCount(selectedItem); index = 1 }
            setupSliceCriteria(rp)
            navigateToTyping()
            Qt.callLater(function() { appBridge.loadLocalArticleSegment(id, index, size) })
        } else if (currentSource === "trainer") {
            var tid = SrcBehav.trainerId(selectedItem)
            if (!tid) { errorMessage = qsTr("词库缺少 ID"); return }
            if (fullText) { size = SrcBehav.trainerEntryCount(selectedItem); index = 1 }
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
        // custom 来源字数校验（依赖 textLoadPanel，留在 hub）
        if (currentSource === "custom") return SrcBehav.customTextLen() > 0
        // registry 额外等待单篇加载完成
        if (currentSource === "registry") return selectedItem !== null && !registryLoading
        // jisubei 需要服务端内容提前拉回（loadSelectedItem 依赖 previewContent）
        if (currentSource === "jisubei")
            return selectedItem !== null && previewContent.length > 0
        // local / trainer 本地读取，选中即可载文
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

        // ---- 顶部来源切换（自定义 pill 导航，背景与高亮完全同高） ----
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 40

            Rectangle {
                anchors.fill: parent
                radius: 8
                color: Theme.currentTheme.colors.subtleColor
                border.color: Theme.currentTheme.colors.dividerBorderColor
                border.width: 1
            }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 3
                spacing: 2

                Repeater {
                    model: root.sourceKeys.length

                    Rectangle {
                        id: pill
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 6
                        property bool isSelected: index === root.currentSourceIndex
                        color: isSelected ? Theme.currentTheme.colors.controlFillColor : "transparent"
                        border.color: isSelected ? Theme.currentTheme.colors.dividerBorderColor : "transparent"
                        border.width: isSelected ? 1 : 0

                        Row {
                            anchors.centerIn: parent
                            spacing: 5

                            IconWidget {
                                anchors.verticalCenter: parent.verticalCenter
                                icon: root.sourceIcons[index]
                                color: isSelected ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textSecondaryColor
                                visible: icon !== ""
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.sourceLabels[index]
                                typography: Typography.Body
                                color: isSelected ? Theme.currentTheme.colors.textColor : Theme.currentTheme.colors.textSecondaryColor
                                font.weight: isSelected ? Font.DemiBold : Font.Normal
                            }
                        }

                        MouseArea {
                            id: pillArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.currentSource = root.sourceKeys[index]
                        }

                        Rectangle {
                            anchors.fill: parent
                            radius: 6
                            color: Theme.currentTheme.colors.subtleSecondaryColor
                            opacity: pillArea.containsMouse && !isSelected ? 0.6 : 0
                            z: -1
                        }
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
                    onItemClicked: function(originalIndex) { root.selectListItem("jisubei", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.loadTextList("jisubei") }
                }

                TextSourceListPanel {
                    title: qsTr("文章")
                    icon: "ic_fluent_document_text_20_regular"
                    sourceItems: root.localItems
                    loading: root.currentSource === "local" && (appBridge ? appBridge.localArticleLoading : false)
                    emptyText: qsTr("暂无本地文章")
                    onItemClicked: function(originalIndex) { root.selectListItem("local", originalIndex) }
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
                    onItemClicked: function(originalIndex) { root.selectListItem("registry", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.refreshCatalog() }
                }

                TextSourceListPanel {
                    title: qsTr("词库")
                    icon: "ic_fluent_text_bullet_list_square_20_regular"
                    sourceItems: root.trainerItems
                    loading: root.currentSource === "trainer" && (appBridge ? appBridge.trainerLoading : false)
                    emptyText: qsTr("暂无练单器词库")
                    onItemClicked: function(originalIndex) { root.selectListItem("trainer", originalIndex) }
                    onRefreshRequested: { if (appBridge) appBridge.loadTrainers() }
                }

                Item {
                    // 卡片背景（与其它来源的 TextSourceListPanel 视觉高度一致）
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
                            visible: SrcBehav.capabilities[root.currentSource].supportsRefresh
                            enabled: !root.currentSourceLoading()
                            onClicked: root.loadCurrentSource()
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("继续上次进度")
                            visible: SrcBehav.capabilities[root.currentSource].supportsProgress && root.canContinue()
                            enabled: root.canContinue()
                            onClicked: root.continueLastProgress()
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("载入跟打")
                            highlighted: root.readyForLoad
                            enabled: root.readyForLoad
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
                textLoadPanel.startSlice = 1
                root.startCustomTyping(rp)
                return
            }
            appBridge.prepareSliceProgressRestore(appBridge.getProgressKey(root.progressKeyType(), _restoreId), _restoreTitle)
            var settings = JSON.parse(appBridge.getRestoredSliceSettings())
            root.navigateToTyping()
            SliceHelpers.startWithCriteria(
                appBridge, null,
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
                        appBridge.loadLocalArticleSegment(SrcBehav.articleId(root.selectedItem), 1, size)
                    } else if (_source === "trainer") {
                        appBridge.loadTrainerSegment(SrcBehav.trainerId(root.selectedItem), 1, size)
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
                root._syncToCurrentList(texts)
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
                var sourceKey = SrcBehav.entrySourceKey(root.selectedItem)
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
            if (root.active && root.currentSource === "registry") {
                root._syncToCurrentList(catalog)
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
                root._syncToCurrentList(articles)
                root.errorMessage = ""
            }
        }
        function onLocalArticlesLoadFailed(message) {
            if (root.active && root.currentSource === "local") { root.errorMessage = message; root.statusMessage = "" }
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
        function onTrainersLoaded(items) {
            if (root.active && root.currentSource === "trainer") {
                root._syncToCurrentList(items)
                root.errorMessage = ""
            }
        }
        function onTrainersLoadFailed(message) {
            if (root.active && root.currentSource === "trainer") { root.errorMessage = message; root.statusMessage = "" }
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
}
