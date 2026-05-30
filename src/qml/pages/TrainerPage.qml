import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"

Item {
    id: trainerPage
    property bool active: false

    property int selectedTrainerIndex: -1
    property var selectedTrainer: null
    property string errorMessage: ""
    property string statusMessage: ""
    property bool hasProgress: false

    // 分片模式开关（true=分片，false=全文）
    property bool sliceModeChecked: true

    function trainerId(item) {
        if (!item)
            return "";
        return item.trainerId || item.trainer_id || item.id || "";
    }

    function trainerTitle(item) {
        if (!item)
            return qsTr("未选择词库");
        return item.title || item.name || trainerId(item) || qsTr("未命名词库");
    }

    function trainerEntryCount(item) {
        if (!item)
            return 0;
        return item.entryCount || item.entry_count || item.count || 0;
    }

    function selectTrainer(index) {
        if (index < 0 || index >= trainerListModel.count) {
            selectedTrainerIndex = -1;
            selectedTrainer = null;
            return;
        }
        selectedTrainerIndex = index;
        selectedTrainer = trainerListModel.get(index);
        trainerListView.currentIndex = index;
        errorMessage = "";
        statusMessage = qsTr("已选择：") + trainerTitle(selectedTrainer);
        checkProgress();
    }

    function checkProgress() {
        if (selectedTrainer && appBridge) {
            hasProgress = appBridge.hasSliceProgress(appBridge.getProgressKey("trainer", trainerId(selectedTrainer)), trainerTitle(selectedTrainer));
        } else {
            hasProgress = false;
        }
    }

    function continueLastProgress() {
        if (!appBridge || !selectedTrainer) {
            errorMessage = qsTr("请选择一个词库");
            return;
        }
        var idValue = trainerId(selectedTrainer);
        if (!idValue) {
            errorMessage = qsTr("词库缺少可加载的 ID");
            return;
        }

        var progressKey = appBridge.getProgressKey("trainer", idValue);
        var infoJson = appBridge.getSliceProgressInfo(progressKey, trainerTitle(selectedTrainer));
        if (!infoJson || infoJson.length === 0) {
            // 无进度，直接开始
            loadSelectedTrainer();
            return;
        }

        progressRestoreDialog.progressInfo = JSON.parse(infoJson);
        progressRestoreDialog._trainerId = idValue;
        progressRestoreDialog._trainerTitle = trainerTitle(selectedTrainer);
        progressRestoreDialog.open();
    }

    function syncTrainers(items) {
        trainerListModel.clear();
        if (items) {
            for (var i = 0; i < items.length; i++)
                trainerListModel.append(items[i]);
        }
        if (trainerListModel.count > 0)
            selectTrainer(0);
        else
            selectTrainer(-1);
    }

    function refreshTrainers() {
        if (!appBridge)
            return;
        errorMessage = "";
        statusMessage = qsTr("正在扫描练单器词库...");
        appBridge.loadTrainers();
    }

    function pushTypingPage() {
        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
        }
    }

    function loadSelectedSegment() {
        if (!appBridge || !selectedTrainer) {
            errorMessage = qsTr("请选择一个词库");
            return;
        }
        var idValue = trainerId(selectedTrainer);
        if (!idValue) {
            errorMessage = qsTr("词库缺少可加载的 ID");
            return;
        }
        // 非恢复流程：清除可能残留的待恢复进度
        appBridge.clearPendingRestore();

        var index = Math.max(1, Math.min(sliceSettingsPanel.startSlice, sliceSettingsPanel.totalSlices));
        var groupSize = sliceSettingsPanel.sliceSize;
        var fullText = !trainerPage.sliceModeChecked;

        if (fullText) {
            groupSize = trainerEntryCount(selectedTrainer);
            index = 1;
        }

        errorMessage = "";
        statusMessage = fullText ? qsTr("正在载入全文...") : qsTr("正在打开第 %1 段...").arg(index);

        // 自动推进参数通过 SliceCriteriaPanel 组件设置
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

        pushTypingPage();

        Qt.callLater(function () {
            if (appBridge) {
                if (fullText) {
                    appBridge.loadTrainerSegment(idValue, 1, groupSize);
                } else {
                    appBridge.loadTrainerSegment(idValue, index, groupSize);
                }
            }
        });
    }

    function runTrainerNavigation(action) {
        if (!appBridge)
            return;
        pushTypingPage();
        Qt.callLater(function () {
            if (appBridge)
                action();
        });
    }

    onActiveChanged: {
        if (active && appBridge)
            refreshTrainers();
    }

    ListModel {
        id: trainerListModel
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
                text: qsTr("练单器")
                elide: Text.ElideRight
            }

            Text {
                Layout.preferredWidth: 160
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: appBridge && appBridge.trainerLoading ? qsTr("扫描中...") : qsTr("%1 个词库").arg(trainerListModel.count)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                running: appBridge ? appBridge.trainerLoading : false
                visible: running
            }

            ToolButton {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !(appBridge && appBridge.trainerLoading)
                flat: true
                onClicked: refreshTrainers()
                ToolTip {
                    text: qsTr("刷新")
                    visible: parent.hovered

                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

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
                            icon: "ic_fluent_text_bullet_list_square_20_regular"
                            color: Theme.currentTheme.colors.primaryColor
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: qsTr("词库")
                            elide: Text.ElideRight
                        }
                    }

                    ListView {
                        id: trainerListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: trainerListModel
                        currentIndex: selectedTrainerIndex

                        QQC.ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            width: trainerListView.width
                            height: 58
                            radius: 6
                            color: index === selectedTrainerIndex ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectTrainer(index)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                IconWidget {
                                    Layout.preferredWidth: 18
                                    Layout.preferredHeight: 18
                                    icon: "ic_fluent_text_bullet_list_square_20_regular"
                                    color: index === selectedTrainerIndex ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textSecondaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Body
                                        text: trainerTitle(model)
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: qsTr("%1 项").arg(trainerEntryCount(model))
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
                            text: appBridge && appBridge.trainerLoading ? qsTr("正在扫描...") : qsTr("暂无练单器词库")
                            horizontalAlignment: Text.AlignHCenter
                            visible: trainerListModel.count === 0
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

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
                                text: trainerTitle(selectedTrainer)
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.currentTheme.colors.cardBorderColor
                        }

                        // --- 分片设置（复用组件）---
                        SliceSettingsPanel {
                            id: sliceSettingsPanel
                            Layout.fillWidth: true
                            sliceModeChecked: trainerPage.sliceModeChecked
                            contentLength: selectedTrainer ? trainerEntryCount(selectedTrainer) : 0
                            sliceSize: 100
                            startSlice: 1
                            onSliceModeCheckedChanged: trainerPage.sliceModeChecked = sliceModeChecked
                        }

                        // --- 达标条件（复用组件）---
                        SliceCriteriaPanel {
                            id: sliceCriteriaPanel
                            Layout.fillWidth: true
                            visible: trainerPage.sliceModeChecked
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
                                enabled: !(appBridge && appBridge.trainerLoading)
                                onClicked: refreshTrainers()
                            }

                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("载入跟打")
                                highlighted: true
                                enabled: selectedTrainer !== null && !(appBridge && appBridge.trainerLoading)
                                onClicked: loadSelectedSegment()
                            }

                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("继续上次进度")
                                visible: hasProgress
                                enabled: selectedTrainer !== null && !(appBridge && appBridge.trainerLoading)
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

        function onTrainersLoaded(items) {
            syncTrainers(items);
            statusMessage = trainerListModel.count > 0 ? qsTr("已加载 %1 个词库").arg(trainerListModel.count) : qsTr("未找到练单器词库");
            errorMessage = "";
        }

        function onTrainersLoadFailed(message) {
            errorMessage = message;
            statusMessage = "";
        }

        function onTrainerSegmentLoaded(segment) {
            var title = segment && segment.title ? segment.title : trainerTitle(selectedTrainer);
            statusMessage = qsTr("已载入：") + title;
            errorMessage = "";
        }

        function onTrainerSegmentLoadFailed(message) {
            errorMessage = message;
        }

        function onTrainerLoadingChanged() {
            if (appBridge && appBridge.trainerLoading)
                statusMessage = qsTr("正在处理练单器词库...");
        }
    }

    function _startWithCriteria(trainerId, index) {
        var settings = appBridge ? JSON.parse(appBridge.getRestoredSliceSettings()) : {};
        var groupSize = settings.slice_size > 0 ? settings.slice_size : sliceSettingsPanel.sliceSize;
        errorMessage = "";
        statusMessage = qsTr("正在恢复进度...");
        if (appBridge) {
            var criteriaOn = settings.condition_on !== undefined ? settings.condition_on : sliceCriteriaPanel.conditionChecked;
            appBridge.setSliceCriteria(
                criteriaOn ? (settings.key_stroke_min || sliceCriteriaPanel.keyStrokeMinValue) : 0,
                criteriaOn ? (settings.speed_min || sliceCriteriaPanel.speedMinValue) : 0,
                criteriaOn ? (settings.accuracy_min || sliceCriteriaPanel.accuracyMinValue) : 0,
                criteriaOn ? (settings.pass_count_min || sliceCriteriaPanel.passCountMinValue) : 1,
                criteriaOn ? (settings.on_fail_action || sliceCriteriaPanel.onFailActionValue) : "none",
                settings.advance_mode || sliceCriteriaPanel.advanceModeValue,
                settings.full_shuffle !== undefined ? settings.full_shuffle : sliceSettingsPanel.fullShuffleChecked,
                settings.auto_decrease_enabled !== undefined ? settings.auto_decrease_enabled : sliceCriteriaPanel.autoDecreaseEnabled,
                settings.key_stroke_decrease || sliceCriteriaPanel.keyStrokeDecreaseValue,
                settings.speed_decrease || sliceCriteriaPanel.speedDecreaseValue,
                settings.accuracy_decrease || sliceCriteriaPanel.accuracyDecreaseValue
            );
        }
        pushTypingPage();
        Qt.callLater(function () {
            if (appBridge)
                appBridge.loadTrainerSegment(trainerId, index, groupSize);
        });
    }

    SliceProgressRestoreDialog {
        id: progressRestoreDialog
        property string _trainerId: ""
        property string _trainerTitle: ""
        onRestoreAccepted: {
            appBridge.prepareSliceProgressRestore(appBridge.getProgressKey("trainer", _trainerId), _trainerTitle);
            trainerPage._startWithCriteria(_trainerId, 1);
        }
        onStartFresh: {
            appBridge.applySliceProgressRestore(appBridge.getProgressKey("trainer", _trainerId), false, _trainerTitle);
            trainerPage._startWithCriteria(_trainerId, 1);
        }
    }
}
