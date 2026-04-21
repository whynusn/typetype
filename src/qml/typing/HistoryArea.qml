import QtQuick 2.15
import QtQuick.Controls
import Qt.labs.qmlmodels
import RinUI

Pane {
    id: root
    property int rowHeight: 30
    property alias tableModel: tableView.model

    padding: 0

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

        model: ["速度", "击键", "码长", "错字数", "回改", "退格", "字数", "时间", "日期"]

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
            TableModelColumn { display: "speed" }
            TableModelColumn { display: "keyStroke" }
            TableModelColumn { display: "codeLength" }
            TableModelColumn { display: "wrongNum" }
            TableModelColumn { display: "correctionCount" }
            TableModelColumn { display: "backspaceCount" }
            TableModelColumn { display: "charNum" }
            TableModelColumn { display: "time" }
            TableModelColumn { display: "date" }
        }

        // 按比例分配列宽，自适应表格总宽度
        columnWidthProvider: function (column) {
            var totalWidth = tableView.width;
            // 权重：速度 1.2, 击键 1, 码长 1, 错字数 1, 回改 0.8, 退格 0.8, 字数 1, 时间 1, 日期 1.8
            var weights = [1.2, 1, 1, 1, 0.8, 0.8, 1, 1, 1.8];
            var totalWeight = 0;
            for (var i = 0; i < weights.length; i++) totalWeight += weights[i];
            return Math.floor(totalWidth * weights[column] / totalWeight);
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
                text: model.display
                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : palette.text
                font.pixelSize: 13
            }
        }

        // 宽度变化时刷新列宽
        onWidthChanged: forceLayout()
    }
}
