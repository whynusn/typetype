import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"
import "../components"

Item {
    id: root
    property bool active: false
    property bool hasProgress: false

    function checkProgress() {
        var text = textLoadPanel.contentText;
        if (text && text.length > 0 && appBridge) {
            hasProgress = appBridge.hasSliceProgress(text);
        } else {
            hasProgress = false;
        }
    }

    function continueLastProgress() {
        var text = textLoadPanel.contentText;
        if (!text || !appBridge) return;

        var infoJson = appBridge.getSliceProgressInfo(text);
        if (!infoJson || infoJson.length === 0) {
            // 无进度，直接开始
            textLoadPanel.startSlice = 1;
            startSliceTyping();
            return;
        }

        progressRestoreDialog.progressInfo = JSON.parse(infoJson);
        progressRestoreDialog.open();
    }

    function startSliceTyping(restoredProgress) {
        var text = textLoadPanel.contentText;
        if (!text) return;

        if (sliceCriteriaPanel.validationMessage) return;

        var sliceSize = textLoadPanel.sliceSize;
        var fullText = !textLoadPanel.sliceModeChecked;
        var openCondition = sliceCriteriaPanel.conditionChecked && textLoadPanel.sliceModeChecked;
        var startSlice = textLoadPanel.startSlice;

        if (fullText) {
            sliceSize = text.length;
            startSlice = 1;
        }

        var ks = sliceCriteriaPanel.keyStrokeMinValue;
        var spd = sliceCriteriaPanel.speedMinValue;
        var acc = sliceCriteriaPanel.accuracyMinValue;
        var pc = sliceCriteriaPanel.passCountMinValue;
        var onFail = sliceCriteriaPanel.onFailActionValue;
        var adEn = sliceCriteriaPanel.autoDecreaseEnabled;
        var ksDec = sliceCriteriaPanel.keyStrokeDecreaseValue;
        var spdDec = sliceCriteriaPanel.speedDecreaseValue;
        var accDec = sliceCriteriaPanel.accuracyDecreaseValue;
        var sourceKey = textLoadPanel.selectedSourceKey;
        var advanceMode = sliceCriteriaPanel.advanceModeValue;
        var fullShuffle = textLoadPanel.fullShuffleChecked;

        if (appBridge) {
            // 1. 先保存偏好
            appBridge.saveSliceMetricsPrefs(ks, spd, acc, pc, onFail, adEn, ksDec, spdDec, accDec);
            // 2. 设置推进参数（供后续分片使用）
            appBridge.setSliceCriteria(
                ks, spd, acc, pc,
                openCondition ? onFail : "none",
                advanceMode, fullShuffle,
                adEn, ksDec, spdDec, accDec
            );
        }

        // 3. 先导航到 TypingPage（确保 onTextLoaded 信号处理器可用）
        if (Window.window && Window.window.navigationView)
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));

        // 4. 等 TypingPage 激活后再载文（Qt.callLater 确保在当前事件循环之后执行）
        Qt.callLater(function() {
            if (!appBridge) return;
            var title = textLoadPanel.selectedSourceLabel || qsTr("自定义文本");
            if (fullText) {
                appBridge.loadFullText(text, sourceKey, title);
            } else {
                appBridge.setupSliceMode(
                    text, sliceSize, startSlice,
                    ks, spd, acc, pc,
                    openCondition ? onFail : "none",
                    adEn, ksDec, spdDec, accDec,
                    restoredProgress || "",
                    title
                );
            }
        });
    }

    onActiveChanged: {
        if (active && appBridge) {
            var prefs = appBridge.loadSliceMetricsPrefs();
            if (prefs && prefs.key_stroke_min !== undefined) {
                sliceCriteriaPanel.keyStrokeMinValue = prefs.key_stroke_min;
                sliceCriteriaPanel.speedMinValue = prefs.speed_min || 100;
                sliceCriteriaPanel.accuracyMinValue = prefs.accuracy_min || 95;
                sliceCriteriaPanel.passCountMinValue = prefs.pass_count_min || 1;
                if (prefs.on_fail_action === "shuffle") sliceCriteriaPanel.onFailActionValue = "shuffle";
                else if (prefs.on_fail_action === "retype") sliceCriteriaPanel.onFailActionValue = "retype";
                else sliceCriteriaPanel.onFailActionValue = "none";
                sliceCriteriaPanel.autoDecreaseEnabled = prefs.auto_decrease_enabled || false;
                sliceCriteriaPanel.keyStrokeDecreaseValue = prefs.key_stroke_decrease || 0.0;
                sliceCriteriaPanel.speedDecreaseValue = prefs.speed_decrease || 0;
                sliceCriteriaPanel.accuracyDecreaseValue = prefs.accuracy_decrease || 0;
            }
            checkProgress();
        }
    }

    // 监听文本内容变化，检查是否有可恢复的历史进度
    Connections {
        target: textLoadPanel
        enabled: root.active
        function onContentTextChanged() {
            root.checkProgress();
        }
    }

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

            Text {
                Layout.fillWidth: true
                typography: Typography.Title
                text: qsTr("自定义载文")
                elide: Text.ElideRight
            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        Flickable {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: columnLayout.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: columnLayout
                width: parent.width
                spacing: 10

                TextLoadPanel {
                    id: textLoadPanel
                    Layout.fillWidth: true
                    compactMode: true
                }

                SliceCriteriaPanel {
                    id: sliceCriteriaPanel
                    Layout.fillWidth: true
                }

                Item {
                    Layout.fillHeight: true
                }

                Text {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: textLoadPanel.validationMessage || sliceCriteriaPanel.validationMessage || ""
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true; Layout.preferredHeight: 36; spacing: 8
                    Item { Layout.fillWidth: true }
                    Button {
                        Layout.preferredHeight: 34
                        text: qsTr("载入跟打")
                        highlighted: true
                        enabled: textLoadPanel.contentText.length > 0 && textLoadPanel.validationMessage === "" && sliceCriteriaPanel.validationMessage === ""
                        onClicked: root.startSliceTyping()
                    }
                    Button {
                        Layout.preferredHeight: 34
                        text: qsTr("继续上次进度")
                        visible: hasProgress
                        enabled: textLoadPanel.contentText.length > 0 && textLoadPanel.validationMessage === "" && sliceCriteriaPanel.validationMessage === ""
                        onClicked: root.continueLastProgress()
                    }
                }
            }
        }
    }

    SliceProgressRestoreDialog {
        id: progressRestoreDialog
        onRestoreAccepted: {
            var key = textLoadPanel.contentText;
            var rp = appBridge.applySliceProgressRestore(key, true);
            textLoadPanel.startSlice = 1;
            root.startSliceTyping(rp);
        }
        onStartFresh: {
            appBridge.applySliceProgressRestore(textLoadPanel.contentText, false);
            textLoadPanel.startSlice = 1;
            root.startSliceTyping();
        }
    }
}
