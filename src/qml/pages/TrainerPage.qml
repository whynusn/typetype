import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

Item {
    id: trainerPage
    property bool active: false

    property int selectedTrainerIndex: -1
    property var selectedTrainer: null
    property string errorMessage: ""
    property string statusMessage: ""

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

    function segmentCount() {
        var total = trainerEntryCount(selectedTrainer);
        if (total <= 0)
            return 1;
        return Math.max(1, Math.ceil(total / Math.max(1, groupSizeSpin.value)));
    }

    function clampSegmentIndex() {
        segmentIndexSpin.to = Math.max(1, segmentCount());
        if (segmentIndexSpin.value > segmentIndexSpin.to)
            segmentIndexSpin.value = segmentIndexSpin.to;
        if (segmentIndexSpin.value < 1)
            segmentIndexSpin.value = 1;
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
        clampSegmentIndex();
        errorMessage = "";
        statusMessage = qsTr("已选择：") + trainerTitle(selectedTrainer);
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
        var index = Math.max(1, Math.min(segmentIndexSpin.value, segmentCount()));
        var groupSize = Math.max(1, groupSizeSpin.value);
        errorMessage = "";
        statusMessage = qsTr("正在打开第 %1 组...").arg(index);
        pushTypingPage();
        Qt.callLater(function() {
            if (appBridge) {
                appBridge.loadTrainerSegment(idValue, index, groupSize);
            }
        });
    }

    function runTrainerNavigation(action) {
        if (!appBridge)
            return;
        pushTypingPage();
        Qt.callLater(function() {
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

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            width: trainerListView.width
                            height: 58
                            radius: 6
                            color: index === selectedTrainerIndex
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : "transparent"

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
                                    color: index === selectedTrainerIndex
                                        ? Theme.currentTheme.colors.primaryColor
                                        : Theme.currentTheme.colors.textSecondaryColor
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
                            text: trainerTitle(selectedTrainer)
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        spacing: 8

                        Text {
                            Layout.preferredWidth: 72
                            typography: Typography.Body
                            text: qsTr("每组数量")
                        }

                        SpinBox {
                            id: groupSizeSpin
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 34
                            from: 1
                            to: 99999
                            value: 20
                            editable: true
                            stepSize: 5
                            onValueChanged: clampSegmentIndex()
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("共 %1 组").arg(segmentCount())
                            elide: Text.ElideRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        spacing: 8

                        Text {
                            Layout.preferredWidth: 72
                            typography: Typography.Body
                            text: qsTr("组序号")
                        }

                        SpinBox {
                            id: segmentIndexSpin
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 34
                            from: 1
                            to: 1
                            value: 1
                            editable: true
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("范围 1-%1").arg(segmentIndexSpin.to)
                            elide: Text.ElideRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        spacing: 8

                        Button {
                            text: qsTr("上一组")
                            enabled: !(appBridge && appBridge.trainerLoading)
                            onClicked: runTrainerNavigation(function() { appBridge.loadPreviousTrainerSegment(); })
                        }

                        Button {
                            text: qsTr("当前组")
                            enabled: !(appBridge && appBridge.trainerLoading)
                            onClicked: runTrainerNavigation(function() { appBridge.loadCurrentTrainerSegment(); })
                        }

                        Button {
                            text: qsTr("下一组")
                            enabled: !(appBridge && appBridge.trainerLoading)
                            onClicked: runTrainerNavigation(function() { appBridge.loadNextTrainerSegment(); })
                        }

                        Button {
                            text: qsTr("乱序")
                            enabled: !(appBridge && appBridge.trainerLoading)
                            onClicked: runTrainerNavigation(function() { appBridge.shuffleCurrentTrainerGroup(); })
                        }
                    }

                    Item {
                        Layout.fillHeight: true
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        typography: Typography.Caption
                        color: errorMessage.length > 0
                            ? Theme.currentTheme.colors.systemCriticalColor
                            : Theme.currentTheme.colors.textSecondaryColor
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
            statusMessage = trainerListModel.count > 0
                ? qsTr("已加载 %1 个词库").arg(trainerListModel.count)
                : qsTr("未找到练单器词库");
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
}
