import QtQuick 2.15
import QtQuick.Controls
import Qt.labs.qmlmodels

Pane {
    id: root
    //color: palette.mid
    property int rowHeight: 20
    property int fontSize: 20
    property string fontFamily: ""
    property alias tableModel: tableView.model

    // 水平表头：拖动它来调整列宽
    HorizontalHeaderView {
        id: horizontalHeader

        anchors.left: tableView.left
        anchors.top: parent.top

        syncView: tableView  // 必须同步到 TableView
        boundsBehavior: Flickable.StopAtBounds  // 拖到边界就停，不允许再拖出去
        clip: true

        property int headerRowHeight: root.rowHeight
        property int headerFontSize: root.fontSize
        property string headerFontFamily: root.fontFamily
        property color headerBackgroundColor: "#A9A9A9" // 表头灰色
        property color normalBackgroundColor: "#D3D3D3"
        property color textColor: palette.windowText

        // 表头每列的标题
        model: ["速度", "击键", "码长", "错字数", "字数", "时间", "日期"]

        // 自定义每个表头单元格的样式
        delegate: Rectangle {
            required property int column
            required property var model
            required property var headerView   // 可选：访问 headerView 自身

            implicitHeight: headerView.headerRowHeight

            // 背景颜色、边框等
            color: headerView.headerBackgroundColor
            border.color: headerView.normalBackgroundColor

            // 文字内容
            Text {
                anchors.centerIn: parent
                text: typeof modelData !== "undefined" ? modelData : ""
                color: headerView.textColor
                font.pixelSize: headerView.headerFontSize
                font.family: headerView.headerFontFamily
                font.bold: true
            }

            // 可选：鼠标悬停高亮
            /*
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onEntered: parent.color =palette.highlight
                onExited: parent.color = palette.window
            }
             */
        }

        // resizableColumns 默认就是 true，
        // 写出来只是更明确，这里可以省略：
        resizableColumns: true
    }

    TableView {
        id: tableView
        //columnSpacing: 1
        //rowSpacing: 1

        anchors.left: parent.left
        anchors.top: horizontalHeader.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom

        boundsBehavior: Flickable.StopAtBounds  // 拖到边界就停，不允许再拖出去
        clip: true // 超出边界就裁剪

        model: TableModel {

            TableModelColumn {
                display: "speed"
            }
            TableModelColumn {
                display: "keyStroke"
            }
            TableModelColumn {
                display: "codeLength"
            }
            TableModelColumn {
                display: "wrongNum"
            }
            TableModelColumn {
                display: "charNum"
            }
            TableModelColumn {
                display: "time"
            }
            TableModelColumn {
                display: "date"
            }

            /*
            rows: [
                {
                    speed: 120.35,
                    keyStroke: 2.8,
                    codeLength: 3.5,
                    charNum: 314,
                    date: "2026-01-01"
                },
            ]
             */
        }

        // 核心：根据列索引返回不同宽度
        columnWidthProvider: function (column) {
            switch (column) {
            case 0:
                return 100;
            case 6:
                return 240;
            default:
                return 80;
            }
        }

        // 每个单元格的样式
        delegate: Rectangle {
            required property int row
            required property int column
            required property var model

            //implicitWidth: 150   // 列宽
            implicitHeight: root.rowHeight
            border.color: palette.mid

            // 普通行：使用 palette.base
            // 在浅色模式下是白色，深色模式下是深黑/深灰
            // 为了好看，我们可以利用系统的 alternateBase 做隔行变色（可选）
            color: row % 2 === 0 ? palette.base : palette.alternateBase

            Text {
                anchors.centerIn: parent
                text: model.display
                color: row === 0 ? palette.buttonText : palette.text
                font.pixelSize: root.fontSize
                font.family: root.fontFamily
            }
        }
    }
}
