import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

Frame {
    id: root
    radius: 6
    hoverable: false
    padding: 8

    // --- 外部可读写属性 ---
    property bool sliceModeChecked: true  // true=分片，false=全文
    property int sliceSize: 100
    property int startSlice: 1
    property bool fullShuffleChecked: false
    property int contentLength: 0

    // 总片段数
    readonly property int totalSlices: sliceSize > 0 ? Math.max(1, Math.ceil(contentLength / sliceSize)) : 1

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

            Item { Layout.fillWidth: true }

            Text {
                text: qsTr("共 %1 段").arg(root.totalSlices)
                font.pixelSize: 11
                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
            }

            CheckBox {
                id: sliceModeCheck
                text: qsTr("开启")
                checked: root.sliceModeChecked
                onCheckedChanged: root.sliceModeChecked = checked
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // 每段字数
        RowLayout {
            visible: root.sliceModeChecked
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            spacing: 8

            Text {
                Layout.preferredWidth: 72
                typography: Typography.Body
                text: qsTr("每段字数")
            }

            SpinBox {
                id: sliceSizeSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 1
                to: 99999
                value: root.sliceSize
                stepSize: 5
                editable: true
                onValueChanged: root.sliceSize = value
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                text: qsTr("共 %1 段").arg(root.totalSlices)
                elide: Text.ElideRight
            }
        }

        // 段序号
        RowLayout {
            visible: root.sliceModeChecked
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            spacing: 8

            Text {
                Layout.preferredWidth: 72
                typography: Typography.Body
                text: qsTr("段序号")
            }

            SpinBox {
                id: startSliceSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 1
                to: root.totalSlices
                value: root.startSlice
                editable: true
                onValueChanged: root.startSlice = value
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                text: qsTr("范围 1-%1").arg(startSliceSpin.to)
                elide: Text.ElideRight
            }
        }

        // 全文乱序
        RowLayout {
            visible: root.sliceModeChecked
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: qsTr("全文乱序")
                font.pixelSize: 13
                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
            }

            Item { Layout.fillWidth: true }

            CheckBox {
                text: qsTr("分片前打乱全文")
                checked: root.fullShuffleChecked
                onCheckedChanged: root.fullShuffleChecked = checked
            }
        }
    }
}
