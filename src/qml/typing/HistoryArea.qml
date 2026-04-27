import QtQuick 2.15
import QtQuick.Controls
import Qt.labs.qmlmodels
import RinUI

Pane {
    id: root
    property int rowHeight: 30
    property alias tableModel: tableView.model
    property var defaultColumnWidths: [64, 86, 72, 72, 72, 64, 64, 72, 72, 72, 132]

    padding: 0

    function resetColumnWidths() {
        for (var i = 0; i < defaultColumnWidths.length; i++) {
            tableView.setColumnWidth(i, defaultColumnWidths[i])
        }
    }

    background: Rectangle {
        color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : palette.window
        border.color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        border.width: 1
        radius: 2
    }

    // 水平表头
    HorizontalHeaderView {
        id: horizontalHeader

        anchors.left: tableView.left
        anchors.right: tableView.right
        anchors.top: parent.top

        syncView: tableView
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        resizableColumns: true

        property int headerRowHeight: root.rowHeight
        property color headerBgColor: Theme.currentTheme ? Theme.currentTheme.colors.cardSecondaryColor : "#ececec"
        property color borderColor: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        property color textColor: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : palette.windowText

        model: ["段号", "速度", "击键", "码长", "错字", "回改", "退格", "键准", "字数", "用时", "日期"]

        delegate: Rectangle {
            required property int column
            required property var model
            required property var headerView

            implicitHeight: headerView.headerRowHeight

            color: headerView.headerBgColor
            border.color: headerView.borderColor
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: typeof modelData !== "undefined" ? modelData : ""
                color: headerView.textColor
                font.bold: true
                font.pixelSize: 13
            }
        }
    }

    TableView {
        id: tableView

        anchors.left: parent.left
        anchors.top: horizontalHeader.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom

        boundsBehavior: Flickable.StopAtBounds
        clip: true

        model: TableModel {
            TableModelColumn { display: "segmentNo" }
            TableModelColumn { display: "speed" }
            TableModelColumn { display: "keyStroke" }
            TableModelColumn { display: "codeLength" }
            TableModelColumn { display: "wrongNum" }
            TableModelColumn { display: "correctionCount" }
            TableModelColumn { display: "backspaceCount" }
            TableModelColumn { display: "keyAccuracy" }
            TableModelColumn { display: "charNum" }
            TableModelColumn { display: "time" }
            TableModelColumn { display: "date" }
        }

        delegate: Rectangle {
            required property int row
            required property int column
            required property var model

            implicitHeight: 30
            border.color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : palette.mid
            border.width: 1

            color: row % 2 === 0
                ? (Theme.currentTheme ? Theme.currentTheme.colors.cardColor : palette.base)
                : (Theme.currentTheme ? Theme.currentTheme.colors.cardSecondaryColor : palette.alternateBase)

            Text {
                anchors.centerIn: parent
                text: {
                    var rowData = tableView.model.rows[row];
                    if (!rowData) {
                        return "";
                    }
                    var roleKeyByColumn = [
                        "segmentNo",
                        "speed",
                        "keyStroke",
                        "codeLength",
                        "wrongNum",
                        "correctionCount",
                        "backspaceCount",
                        "keyAccuracy",
                        "charNum",
                        "time",
                        "date"
                    ];
                    var roleKey = roleKeyByColumn[column];
                    if (!roleKey) {
                        return "";
                    }
                    var value = rowData[roleKey];
                    return value === undefined || value === null ? "" : value;
                }
                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : palette.text
                font.pixelSize: 13
            }

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.RightButton
                propagateComposedEvents: true

                onClicked: (mouse) => {
                    if (mouse.button !== Qt.RightButton || !appBridge) {
                        return
                    }
                    var rowData = tableView.model.rows[row]
                    if (rowData && rowData.scoreText) {
                        appBridge.copyToClipboard(rowData.scoreText)
                        copyToast.show()
                    }
                }
            }
        }

        Component.onCompleted: root.resetColumnWidths()
    }

    Rectangle {
        id: copyToast

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        z: 10
        width: copyToastText.implicitWidth + 32
        height: 32
        radius: 6
        visible: false
        opacity: visible ? 1 : 0
        color: Theme.currentTheme ? Theme.currentTheme.colors.systemSuccessBackgroundColor : "#e6f4ea"
        border.color: Theme.currentTheme ? Theme.currentTheme.colors.systemSuccessColor : "#107c10"
        border.width: 1

        Text {
            id: copyToastText

            anchors.centerIn: parent
            text: qsTr("已复制到剪贴板")
            color: Theme.currentTheme ? Theme.currentTheme.colors.systemSuccessColor : "#107c10"
            font.pixelSize: 13
        }

        Timer {
            id: copyToastTimer

            interval: 1600
            onTriggered: copyToast.visible = false
        }

        function show() {
            visible = true
            copyToastTimer.restart()
        }
    }
}
