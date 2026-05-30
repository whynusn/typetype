import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"

Item {
    id: root
    property bool active: false

    property int selectedTextIndex: -1
    property var selectedText: null
    property string errorMessage: ""
    property string statusMessage: ""
    property string textContent: ""
    property int _serverTextId: 0  // 服务端文本 ID，用于排行榜对接
    property bool hasProgress: false

    // 分片模式开关（true=分片，false=全文）
    property bool sliceModeChecked: true

    function textTitle(item) {
        if (!item) return qsTr("未选择文本");
        return item.title || item.name || qsTr("未命名文本");
    }

    function textCharCount(item) {
        if (!item) return 0;
        return item.charCount || item.char_count || 0;
    }

    function selectText(index) {
        if (index < 0 || index >= textListModel.count) {
            selectedTextIndex = -1;
            selectedText = null;
            return;
        }
        selectedTextIndex = index;
        selectedText = textListModel.get(index);
        textListView.currentIndex = index;
        errorMessage = "";
        statusMessage = qsTr("已选择：") + textTitle(selectedText);
        _serverTextId = 0;
        textContent = "";
        checkProgress();

        // 加载选中文本的内容到 TextLoadPanel
        var id = selectedText.id || 0;
        if (id > 0 && appBridge) {
            appBridge.getTextContentById(id);
        }
    }

    function checkProgress() {
        if (!selectedText || !appBridge) {
            hasProgress = false;
            return;
        }
        // 优先使用内容哈希（与 collectSliceResult 保存的 key 一致）
        var text = root.textContent;
        if (text && text.length > 0) {
            hasProgress = appBridge.hasSliceProgress(appBridge.getProgressKey("custom_text", text), textTitle(selectedText));
        } else {
            hasProgress = false;
        }
    }

    function continueLastProgress() {
        if (!appBridge || !selectedText) {
            errorMessage = qsTr("请选择一篇文本");
            return;
        }
        var text = root.textContent;
        if (!text || text.length === 0) {
            errorMessage = qsTr("文本内容尚未加载完成，请稍候");
            return;
        }

        var infoJson = appBridge.getSliceProgressInfo(appBridge.getProgressKey("custom_text", text), textTitle(selectedText));
        if (!infoJson || infoJson.length === 0) {
            // 无进度，直接开始
            loadSelectedText();
            return;
        }

        progressRestoreDialog.progressInfo = JSON.parse(infoJson);
        progressRestoreDialog.open();
    }

    function syncTexts(texts) {
        selectedText = null;
        selectedTextIndex = -1;
        textListModel.clear();
        if (texts) {
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i];
                textListModel.append({
                    id: t.id || 0,
                    title: t.title || "",
                    char_count: t.charCount !== undefined && t.charCount !== null ? t.charCount : 0
                });
            }
        }
        if (textListModel.count > 0) selectText(0);
        else selectText(-1);
    }

    function refreshTexts() {
        if (!appBridge) return;
        errorMessage = "";
        statusMessage = qsTr("正在加载极速杯文本列表...");
        appBridge.loadTextList("jisubei");
    }

    function loadSelectedText(restoredProgress) {
        if (!appBridge || !selectedText) {
            errorMessage = qsTr("请选择一篇文本");
            return;
        }
        // 非恢复流程：清除可能残留的待恢复进度
        if (!restoredProgress) appBridge.clearPendingRestore();

        var text = root.textContent;
        if (!text || text.length === 0) {
            errorMessage = qsTr("文本内容尚未加载完成，请稍候");
            return;
        }

        // 有恢复进度时使用保存的设置，否则用 UI 面板值
        var rp = restoredProgress ? JSON.parse(restoredProgress) : null;
        var rpMetrics = rp ? (rp.metrics || {}) : {};
        var ks = rpMetrics.key_stroke_min !== undefined ? rpMetrics.key_stroke_min : sliceCriteriaPanel.keyStrokeMinValue;
        var spd = rpMetrics.speed_min !== undefined ? rpMetrics.speed_min : sliceCriteriaPanel.speedMinValue;
        var acc = rpMetrics.accuracy_min !== undefined ? rpMetrics.accuracy_min : sliceCriteriaPanel.accuracyMinValue;
        var pc = rpMetrics.pass_count_min !== undefined ? rpMetrics.pass_count_min : sliceCriteriaPanel.passCountMinValue;
        var onFail = rpMetrics.on_fail_action || sliceCriteriaPanel.onFailActionValue;
        var adEn = rpMetrics.auto_decrease_enabled !== undefined ? rpMetrics.auto_decrease_enabled : sliceCriteriaPanel.autoDecreaseEnabled;
        var ksDec = rpMetrics.key_stroke_decrease !== undefined ? rpMetrics.key_stroke_decrease : sliceCriteriaPanel.keyStrokeDecreaseValue;
        var spdDec = rpMetrics.speed_decrease !== undefined ? rpMetrics.speed_decrease : sliceCriteriaPanel.speedDecreaseValue;
        var accDec = rpMetrics.accuracy_decrease !== undefined ? rpMetrics.accuracy_decrease : sliceCriteriaPanel.accuracyDecreaseValue;
        var advanceMode = rp ? (rp.advance_mode || sliceCriteriaPanel.advanceModeValue) : sliceCriteriaPanel.advanceModeValue;
        var fullShuffle = rp && rp.shuffle_seed !== null && rp.shuffle_seed !== undefined ? true : sliceSettingsPanel.fullShuffleChecked;
        var sliceSize = rp && rp.slice_size > 0 ? rp.slice_size : sliceSettingsPanel.sliceSize;
        var startSlice = rp && rp.current_slice > 0 ? rp.current_slice : sliceSettingsPanel.startSlice;
        var openCondition = rp ? (ks > 0 || spd > 0 || acc > 0 || onFail !== "none") : sliceCriteriaPanel.conditionChecked;
        var fullText = !root.sliceModeChecked;

        if (fullText) {
            sliceSize = text.length;
            startSlice = 1;
        }

        if (appBridge) {
            appBridge.saveSliceMetricsPrefs(ks, spd, acc, pc, onFail, adEn, ksDec, spdDec, accDec);
            appBridge.setSliceCriteria(ks, spd, acc, pc, openCondition ? onFail : "none", advanceMode, fullShuffle, adEn, ksDec, spdDec, accDec);
        }

        if (Window.window && Window.window.navigationView)
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));

        Qt.callLater(function() {
            if (!appBridge) return;
            var title = textTitle(selectedText);
            if (fullText) {
                appBridge.loadFullText(text, "jisubei", title);
                if (root._serverTextId > 0)
                    appBridge.setTextId(root._serverTextId);
            } else {
                appBridge.setupSliceMode(text, sliceSize, startSlice, ks, spd, acc, pc, openCondition ? onFail : "none", adEn, ksDec, spdDec, accDec, restoredProgress || "", title);
            }
        });
    }

    onActiveChanged: {
        if (active && appBridge) {
            refreshTexts();
        }
    }

    ListModel { id: textListModel }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            spacing: 8

            ToolButton {
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_left_20_regular"
                flat: true
                onClicked: {
                    if (Window.window && Window.window.navigationView)
                        Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
                }
                ToolTip { text: qsTr("返回"); visible: parent.hovered }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Title
                    text: qsTr("极速杯载文")
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("数据来源：52dazi.cn")
                    elide: Text.ElideRight

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Qt.openUrlExternally("https://www.52dazi.cn/about")
                    }
                }
            }

            Text {
                Layout.preferredWidth: 160
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: appBridge && appBridge.textListLoading ? qsTr("加载中...") : qsTr("%1 篇文本").arg(textListModel.count)
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
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !(appBridge && appBridge.textListLoading)
                flat: true
                onClicked: refreshTexts()
                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 8

            // 左侧：文本列表
            Frame {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                radius: 6; hoverable: false; padding: 8

                ColumnLayout {
                    anchors.fill: parent; spacing: 6

                    RowLayout {
                        Layout.fillWidth: true; Layout.preferredHeight: 24; spacing: 6
                        IconWidget {
                            Layout.preferredWidth: 16; Layout.preferredHeight: 16
                            icon: "ic_fluent_text_bullet_list_square_20_regular"
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
                        id: textListView
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: textListModel
                        currentIndex: selectedTextIndex

                        QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            width: textListView.width; height: 58; radius: 6
                            color: index === selectedTextIndex ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectText(index)
                            }

                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                                IconWidget {
                                    Layout.preferredWidth: 18; Layout.preferredHeight: 18
                                    icon: "ic_fluent_document_text_20_regular"
                                    color: index === selectedTextIndex ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textSecondaryColor
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2
                                    Text { Layout.fillWidth: true; typography: Typography.Body; text: textTitle(model); elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; typography: Typography.Caption; color: Theme.currentTheme.colors.textSecondaryColor; text: qsTr("%1 字").arg(textCharCount(model)); elide: Text.ElideRight }
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent; width: parent.width - 24
                            typography: Typography.Body
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("暂无文本")
                            horizontalAlignment: Text.AlignHCenter
                            visible: textListModel.count === 0
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            // 右侧：文本预览 + 设置
            Frame {
                Layout.fillWidth: true; Layout.fillHeight: true
                radius: 6; hoverable: false; padding: 12

                Flickable {
                    anchors.fill: parent; clip: true
                    contentWidth: width; contentHeight: columnLayout2.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds

                    QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    ColumnLayout {
                        id: columnLayout2
                        width: parent.width; spacing: 10

                        RowLayout {
                            Layout.fillWidth: true; Layout.preferredHeight: 28; spacing: 8
                            IconWidget {
                                Layout.preferredWidth: 18; Layout.preferredHeight: 18
                                icon: "ic_fluent_open_20_regular"
                                color: Theme.currentTheme.colors.primaryColor
                            }
                            Text {
                                Layout.fillWidth: true
                                typography: Typography.BodyStrong
                                text: textTitle(selectedText)
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 1
                            color: Theme.currentTheme.colors.cardBorderColor
                        }

                        // --- 分片设置（复用组件）---
                        SliceSettingsPanel {
                            id: sliceSettingsPanel
                            Layout.fillWidth: true
                            sliceModeChecked: root.sliceModeChecked
                            contentLength: root.textContent.length
                            sliceSize: 100
                            startSlice: 1
                            onSliceModeCheckedChanged: root.sliceModeChecked = sliceModeChecked
                        }

                        // 达标条件
                        SliceCriteriaPanel {
                            id: sliceCriteriaPanel
                            Layout.fillWidth: true
                            visible: root.sliceModeChecked
                        }

                        Item { Layout.fillHeight: true }

                        Text {
                            Layout.fillWidth: true; Layout.preferredHeight: 24
                            typography: Typography.Caption
                            color: errorMessage.length > 0 ? Theme.currentTheme.colors.systemCriticalColor : Theme.currentTheme.colors.textSecondaryColor
                            text: errorMessage.length > 0 ? errorMessage : statusMessage
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true; Layout.preferredHeight: 36; spacing: 8
                            Item { Layout.fillWidth: true }
                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("刷新")
                                enabled: !(appBridge && appBridge.textListLoading)
                                onClicked: refreshTexts()
                            }
                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("载入跟打")
                                highlighted: true
                                enabled: selectedText !== null && textContent.length > 0 && !(appBridge && appBridge.textListLoading)
                                onClicked: root.loadSelectedText()
                            }
                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("继续上次进度")
                                visible: hasProgress
                                enabled: selectedText !== null && !(appBridge && appBridge.textListLoading)
                                onClicked: continueLastProgress()
                            }
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onTextListLoaded(texts) {
            syncTexts(texts);
            statusMessage = textListModel.count > 0 ? qsTr("已加载 %1 篇文本").arg(textListModel.count) : qsTr("未找到文本");
            errorMessage = "";
        }

        function onTextListLoadFailed(message) {
            errorMessage = message;
            statusMessage = "";
        }

        function onTextContentLoaded(textId, content, title) {
            if (root.active) {
                root._serverTextId = textId || 0;
                root.textContent = content;
                statusMessage = qsTr("已载入：") + (title || textTitle(selectedText));
                errorMessage = "";
                root.checkProgress();
            }
        }
    }

    SliceProgressRestoreDialog {
        id: progressRestoreDialog
        onRestoreAccepted: {
            var rp = appBridge.applySliceProgressRestore(appBridge.getProgressKey("custom_text", root.textContent), true, textTitle(selectedText));
            root.loadSelectedText(rp);
        }
        onStartFresh: {
            appBridge.applySliceProgressRestore(appBridge.getProgressKey("custom_text", root.textContent), false, textTitle(selectedText));
            root.loadSelectedText();
        }
    }
}
