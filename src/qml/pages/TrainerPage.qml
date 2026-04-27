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
        statusMessage = qsTr("正在打开第 %1 段...").arg(index);
        // 自动推进参数通过已嵌入的 UI 字段直接设置
        if (appBridge) {
            var criteriaOn = conditionCheck.checked;
            appBridge.setSliceCriteria(criteriaOn ? keyStrokeMinSpin.value : 0, criteriaOn ? speedMinSpin.value : 0, criteriaOn ? accuracyMinSpin.value : 0, criteriaOn ? passCountMinSpin.value : 1, criteriaOn ? onFailActionCombo.currentValue : "none", advanceModeCombo.currentValue, fullShuffleCheck.checked);
        }
        pushTypingPage();
        Qt.callLater(function () {
            if (appBridge)
                appBridge.loadTrainerSegment(idValue, index, groupSize);
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

                    ScrollBar.vertical: ScrollBar {
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

                        // --- 分片设置（包裹所有分片相关控件）---
                        Frame {
                            Layout.fillWidth: true
                            radius: 6
                            hoverable: false
                            padding: 8

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true

                                    Text {
                                        text: qsTr("分片设置")
                                        font.bold: true
                                        font.pixelSize: 13
                                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        text: qsTr("词库条目按每段词数分组，顺序跟打")
                                        font.pixelSize: 11
                                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 1
                                    color: Theme.currentTheme.colors.cardBorderColor
                                }

                                // 每组数量
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 42
                                    spacing: 8

                                    Text {
                                        Layout.preferredWidth: 72
                                        typography: Typography.Body
                                        text: qsTr("每段词数")
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
                                        text: qsTr("共 %1 段").arg(segmentCount())
                                        elide: Text.ElideRight
                                    }
                                }

                                // 组序号
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 42
                                    spacing: 8

                                    Text {
                                        Layout.preferredWidth: 72
                                        typography: Typography.Body
                                        text: qsTr("段序号")
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

                                // 全文乱序
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Text {
                                        text: qsTr("全文乱序")
                                        font.pixelSize: 13
                                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    CheckBox {
                                        id: fullShuffleCheck
                                        text: qsTr("分片前打乱全文")
                                    }
                                }
                            }
                        }

                        // --- 自动推进 ---
                        Frame {
                            Layout.fillWidth: true
                            radius: 6
                            hoverable: false
                            padding: 8

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true

                                    Text {
                                        typography: Typography.BodyStrong
                                        text: qsTr("自动推进")
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    CheckBox {
                                        id: conditionCheck
                                        text: qsTr("开启")
                                    }
                                }

                                Text {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    typography: Typography.Caption
                                    text: qsTr("每段达标后自动跳转下一段，可循环跟打")
                                    wrapMode: Text.Wrap
                                }

                                // 推进模式
                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("推进模式")
                                    }

                                    ComboBox {
                                        id: advanceModeCombo
                                        model: ListModel {
                                            ListElement {
                                                text: qsTr("顺序下一段")
                                                value: "sequential"
                                            }
                                            ListElement {
                                                text: qsTr("随机下一段")
                                                value: "random"
                                            }
                                        }
                                        textRole: "text"
                                        valueRole: "value"
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }

                                // 达标条件
                                Text {
                                    visible: conditionCheck.checked
                                    typography: Typography.Body
                                    text: qsTr("达标条件")
                                }

                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("击键 ≥")
                                    }
                                    SpinBox {
                                        id: keyStrokeMinSpin
                                        Layout.preferredWidth: 128
                                        Layout.preferredHeight: 34
                                        from: 0
                                        to: 99
                                        value: 6
                                        stepSize: 1
                                        editable: true
                                    }
                                    Text {
                                        typography: Typography.Caption
                                        text: qsTr("次/秒")
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }

                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("速度 ≥")
                                    }
                                    SpinBox {
                                        id: speedMinSpin
                                        Layout.preferredWidth: 128
                                        Layout.preferredHeight: 34
                                        from: 0
                                        to: 999
                                        value: 100
                                        stepSize: 10
                                        editable: true
                                    }
                                    Text {
                                        typography: Typography.Caption
                                        text: qsTr("字/分")
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }

                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("键准 ≥")
                                    }
                                    SpinBox {
                                        id: accuracyMinSpin
                                        Layout.preferredWidth: 128
                                        Layout.preferredHeight: 34
                                        from: 0
                                        to: 100
                                        value: 95
                                        stepSize: 5
                                        editable: true
                                    }
                                    Text {
                                        typography: Typography.Caption
                                        text: "%"
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }

                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("连达标 ≥")
                                    }
                                    SpinBox {
                                        id: passCountMinSpin
                                        Layout.preferredWidth: 128
                                        Layout.preferredHeight: 34
                                        from: 1
                                        to: 99
                                        value: 1
                                        stepSize: 1
                                        editable: true
                                    }
                                    Text {
                                        typography: Typography.Caption
                                        text: qsTr("次")
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }

                                Text {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    typography: Typography.Caption
                                    text: qsTr("击键、速度、键准均达标且无错字算一次合格")
                                    wrapMode: Text.Wrap
                                }

                                RowLayout {
                                    visible: conditionCheck.checked
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Text {
                                        typography: Typography.Body
                                        text: qsTr("未达标/有错字")
                                    }

                                    ComboBox {
                                        id: onFailActionCombo
                                        currentIndex: 1
                                        model: ListModel {
                                            ListElement {
                                                text: qsTr("乱序重打")
                                                value: "shuffle"
                                            }
                                            ListElement {
                                                text: qsTr("重打")
                                                value: "retype"
                                            }
                                            ListElement {
                                                text: qsTr("无动作")
                                                value: "none"
                                            }
                                        }
                                        textRole: "text"
                                        valueRole: "value"
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }
                                }
                            }
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
}
