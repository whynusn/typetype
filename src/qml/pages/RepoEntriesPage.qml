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

    // ---- 内部状态 ----
    property bool loading: false
    property string errorMessage: ""

    title: root.sourceLabel || qsTr("条目列表")

    Component.onCompleted: {
        console.log("[RepoEntriesPage] created, entries:", root.entries.length, "label:", root.sourceLabel)
    }

    // ---- 内容 ----
    QQC.ScrollView {
        anchors.fill: parent
        clip: true

        ColumnLayout {
            spacing: 8

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

                    Column {
                        id: entryCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 12
                        spacing: 6

                        Text {
                            text: modelData.title || modelData.entry_id || ""
                            width: parent.width
                            typography: Typography.BodyStrong
                            color: Theme.currentTheme.colors.textColor
                            elide: Text.ElideRight
                        }

                        Text {
                            text: (modelData.char_count || 0) + " 字"
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                        }

                        Text {
                            text: modelData.authority ? "@" + modelData.authority : ""
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            visible: !!modelData.authority
                        }

                        Text {
                            text: modelData.content ? modelData.content.substring(0, 120) : ""
                            width: parent.width
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            visible: !!modelData.content
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
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 40
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
            }
        }
    }
}
