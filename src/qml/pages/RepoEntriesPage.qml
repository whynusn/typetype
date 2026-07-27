import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    id: root

    // ---- 输入 ----
    property string sourceLabel: ""
    property var entries: []

    // ---- 输出 ----
    signal entryClicked(var entry)

    title: root.sourceLabel || qsTr("条目列表")

    // ---- 内容 ----
    ScrollView {
        anchors.fill: parent
        clip: true

        ColumnLayout {
            width: root.width
            spacing: 8
            anchors.margins: 16

            // 条目列表
            Repeater {
                model: root.entries

                delegate: Rectangle {
                    Layout.fillWidth: true
                    height: entryCol.height + 16
                    radius: 8
                    color: Theme.currentTheme.colors.cardColor
                    border.color: Theme.currentTheme.colors.cardBorderColor
                    border.width: 1

                    ColumnLayout {
                        id: entryCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 12
                        spacing: 6

                        Text {
                            text: modelData.title || modelData.entry_id || ""
                            typography: Typography.BodyStrong
                            color: Theme.currentTheme.colors.textColor
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        Text {
                            text: (modelData.char_count || 0) + " 字"
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                        }

                        Text {
                            text: modelData.content ? modelData.content.substring(0, 120) : ""
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            visible: modelData.content
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.entryClicked(modelData)
                    }
                }
            }

            // 空状态
            Text {
                visible: root.entries.length === 0
                text: qsTr("暂无条目")
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 40
            }
        }
    }
}
