import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"

Item {
    id: textLibraryPage
    property bool active: false

    property int selectedEntryIndex: -1
    property var selectedEntry: null
    property string errorMessage: ""
    property string statusMessage: ""
    // 分片模式开关（true=分片，false=全文）
    property bool sliceModeChecked: false
    // 加载自 registry CDN 的正文与标题
    property string loadedContent: ""
    property string loadedTitle: ""

    readonly property var _navigationView: Window.window ? Window.window.navigationView : null

    function entrySourceKey(entry) {
        if (!entry) return "";
        return entry.sourceKey || "";
    }

    function entryLabel(entry) {
        if (!entry) return qsTr("未选择文本");
        return entry.label || entry.sourceKey || "";
    }

    function entryCharCount(entry) {
        if (!entry) return 0;
        if (loadedContent.length > 0) return loadedContent.length;
        return entry.charCount || 0;
    }

    function syncCatalog(catalog) {
        catalogListModel.clear();
        selectedEntry = null;
        selectedEntryIndex = -1;
        loadedContent = "";
        loadedTitle = "";
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                catalogListModel.append({
                    sourceKey: catalog[i].key,
                    label: catalog[i].label || catalog[i].key,
                    description: catalog[i].description || "",
                    charCount: catalog[i].charCount || 0
                });
            }
        }
        if (catalogListModel.count > 0)
            selectEntry(0);
        else
            selectEntry(-1);
    }

    function selectEntry(index) {
        if (index < 0 || index >= catalogListModel.count) {
            selectedEntryIndex = -1;
            selectedEntry = null;
            loadedContent = "";
            loadedTitle = "";
            return;
        }
        selectedEntryIndex = index;
        selectedEntry = catalogListModel.get(index);
        loadedContent = "";
        loadedTitle = "";
        errorMessage = "";
        statusMessage = qsTr("已选择：") + entryLabel(selectedEntry);
    }

    function doAfterLoad() {
        // 校验选中项
        if (!appBridge || !selectedEntry) {
            errorMessage = qsTr("请选择一个文本");
            return;
        }
        var sourceKey = entrySourceKey(selectedEntry);
        if (!sourceKey) {
            errorMessage = qsTr("文本缺少来源 key");
            return;
        }
        // 先通过 CDN 加载 registry 文本内容
        errorMessage = "";
        statusMessage = qsTr("正在从 registry CDN 加载...");
        appBridge.loadLibraryText(sourceKey);
    }

    onActiveChanged: {
        if (active && appBridge) {
            appBridge.loadCatalog();
        }
    }

    ListModel {
        id: catalogListModel
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        // ========== 标题栏 ==========
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            spacing: 8

            ToolButton {
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_left_20_regular"
                flat: true
                onClicked: {
                    if (_navigationView)
                        _navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
                }
                ToolTip { text: qsTr("返回"); visible: parent.hovered }
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Title
                text: qsTr("开源文库")
                elide: Text.ElideRight
            }

            Text {
                Layout.preferredWidth: 160
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: appBridge && appBridge.textListLoading ? qsTr("加载中...") : qsTr("%1 篇文本").arg(catalogListModel.count)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                running: appBridge ? appBridge.textListLoading : false
                visible: running
            }

            ToolButton {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !(appBridge && appBridge.textListLoading)
                flat: true
                onClicked: {
                    if (appBridge) appBridge.refreshCatalog();
                }
                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // ========== 双面板主体 ==========
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            // —— 左：文本列表 ——
            Frame {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                radius: 6
                hoverable: false
                padding: 8

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        spacing: 6

                        IconWidget {
                            Layout.preferredWidth: 16
                            Layout.preferredHeight: 16
                            icon: "ic_fluent_document_text_20_regular"
                            color: Theme.currentTheme.colors.primaryColor
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: qsTr("文本列表")
                            elide: Text.ElideRight
                        }
                    }

                    ListView {
                        id: catalogListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: catalogListModel
                        currentIndex: selectedEntryIndex

                        QQC.ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            width: catalogListView.width
                            height: 58
                            radius: 6
                            color: index === selectedEntryIndex ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectEntry(index)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                IconWidget {
                                    Layout.preferredWidth: 18
                                    Layout.preferredHeight: 18
                                    icon: "ic_fluent_document_text_20_regular"
                                    color: index === selectedEntryIndex ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textSecondaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Body
                                        text: model.label || ""
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: (model.description || "") + (model.charCount > 0 ? " • " + model.charCount + qsTr("字") : "")
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 24
                            typography: Typography.Body
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: appBridge && appBridge.textListLoading ? qsTr("正在加载...") : qsTr("暂无文本")
                            horizontalAlignment: Text.AlignHCenter
                            visible: catalogListModel.count === 0
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            // —— 右：选中文本详情 ——
            Frame {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 6
                hoverable: false
                padding: 12

                Flickable {
                    anchors.fill: parent
                    clip: true
                    contentWidth: width
                    contentHeight: columnLayout.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds

                    QQC.ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    ColumnLayout {
                        id: columnLayout
                        width: parent.width
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
                                text: entryLabel(selectedEntry)
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.currentTheme.colors.cardBorderColor
                        }

                        TextInfoCard {
                            id: textInfoCard
                            title: entryLabel(selectedEntry)
                            textId: null
                            charCount: entryCharCount(selectedEntry)
                            content: loadedContent ? loadedContent.substring(0, 200) : ""
                        }

                        // --- 分片设置（复用组件）---
                        SliceSettingsPanel {
                            id: sliceSettingsPanel
                            Layout.fillWidth: true
                            sliceModeChecked: textLibraryPage.sliceModeChecked
                            contentLength: entryCharCount(selectedEntry)
                            sliceSize: 100
                            startSlice: 1
                            onSliceModeCheckedChanged: textLibraryPage.sliceModeChecked = sliceModeChecked
                        }

                        // --- 达标条件（复用组件）---
                        SliceCriteriaPanel {
                            id: sliceCriteriaPanel
                            Layout.fillWidth: true
                            visible: textLibraryPage.sliceModeChecked
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 24
                            typography: Typography.Caption
                            color: errorMessage.length > 0 ? Theme.currentTheme.colors.systemCriticalColor : Theme.currentTheme.colors.textSecondaryColor
                            text: errorMessage.length > 0 ? errorMessage : statusMessage
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            spacing: 8

                            Item {
                                Layout.fillWidth: true
                            }

                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("刷新")
                                enabled: !(appBridge && appBridge.textListLoading)
                                onClicked: {
                                    if (appBridge) appBridge.refreshCatalog();
                                }
                            }

                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("载入跟打")
                                highlighted: true
                                enabled: selectedEntry !== null && !(appBridge && appBridge.textListLoading)
                                onClicked: doAfterLoad()
                            }
                        }
                    }
                }
            }
        }
    }

    // ========== 信号连接 ==========
    Connections {
        target: appBridge
        enabled: textLibraryPage.active

        function onCatalogLoaded(catalog) {
            syncCatalog(catalog);
            statusMessage = catalogListModel.count > 0
                ? qsTr("已加载 %1 篇 registry 文本").arg(catalogListModel.count)
                : qsTr("暂无 registry 文本");
            errorMessage = "";
        }

        function onCatalogLoadFailed(message) {
            errorMessage = message;
            statusMessage = "";
        }

        function onTextContentLoaded(textId, content, title) {
            // 保存加载自 registry CDN 的内容
            loadedContent = content || "";
            loadedTitle = title || entryLabel(selectedEntry);
            errorMessage = "";
            if (!loadedContent) {
                statusMessage = qsTr("文本为空");
                return;
            }
            statusMessage = qsTr("已载入：") + loadedTitle;

            // 导航前捕获 sourceKey（避免页面销毁后 selectedEntry 变野指针）
            var sourceKey = entrySourceKey(selectedEntry);

            // 设置达标条件
            if (appBridge) {
                var criteriaOn = sliceCriteriaPanel.conditionChecked;
                appBridge.setSliceCriteria(
                    criteriaOn ? sliceCriteriaPanel.keyStrokeMinValue : 0,
                    criteriaOn ? sliceCriteriaPanel.speedMinValue : 0,
                    criteriaOn ? sliceCriteriaPanel.accuracyMinValue : 0,
                    criteriaOn ? sliceCriteriaPanel.passCountMinValue : 1,
                    criteriaOn ? sliceCriteriaPanel.onFailActionValue : "none",
                    sliceCriteriaPanel.advanceModeValue,
                    sliceSettingsPanel.fullShuffleChecked,
                    sliceCriteriaPanel.autoDecreaseEnabled,
                    sliceCriteriaPanel.keyStrokeDecreaseValue,
                    sliceCriteriaPanel.speedDecreaseValue,
                    sliceCriteriaPanel.accuracyDecreaseValue
                );
            }
            // 先导航到跟打页，后用 callLater 发射 textLoaded 信号
            if (_navigationView) {
                _navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
            }
            Qt.callLater(function() {
                if (appBridge && loadedContent) {
                    appBridge.loadFullText(loadedContent, sourceKey, loadedTitle, textId);
                }
            });
        }

        function onTextLoadFailed(message) {
            errorMessage = message;
            statusMessage = "";
            loadedContent = "";
            loadedTitle = "";
        }
    }
}
