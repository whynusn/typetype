import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

// 可折叠文本信息卡（footer 模式），参考 DailyLeaderboard.qml textInfoCard 实现
Frame {
    id: root

    property string title: ""
    property var textId: null
    property int charCount: 0
    property string content: ""
    property string sourceIcon: "ic_fluent_document_text_20_filled"

    visible: title.length > 0

    // 折叠高度 80，展开时根据内容
    property bool _expanded: false

    Layout.fillWidth: true
    Layout.preferredHeight: visible ? (_expanded && content.length > 0 ? Math.min(textContentArea.implicitHeight + 16, 350) : 80) : 0
    radius: 8
    hoverable: false

    // 点击展开/折叠
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (root.content.length > 0)
                root._expanded = !root._expanded
        }
    }

    ColumnLayout {
        id: textContentArea
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 8
        anchors.bottomMargin: 8
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: 12

            IconWidget {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                Layout.alignment: Qt.AlignVCenter
                icon: root.sourceIcon
                color: Theme.currentTheme.colors.primaryColor
            }

            Text {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                typography: Typography.BodyStrong
                text: root.title
                elide: Text.ElideRight
            }

            Text {
                Layout.alignment: Qt.AlignVCenter
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: {
                    var parts = []
                    if (root.textId !== null && root.textId !== undefined && root.textId !== "")
                        parts.push("ID: " + root.textId)
                    parts.push(root.charCount + "字")
                    return parts.join(" · ")
                }
            }

            IconWidget {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
                icon: root._expanded ? "ic_fluent_chevron_up_20_regular" : "ic_fluent_chevron_down_20_regular"
                color: Theme.currentTheme.colors.textSecondaryColor
                visible: root.content.length > 0
            }

            ToolButton {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                Layout.alignment: Qt.AlignVCenter
                icon.name: "ic_fluent_copy_20_regular"
                size: 16
                flat: true
                visible: root._expanded && root.content.length > 0
                onClicked: {
                    if (root.content.length > 0 && appBridge) {
                        appBridge.copyToClipboard(root.content)
                        copyToast.show()
                    }
                }
                ToolTip {
                    text: qsTr("复制全文")
                    parent: parent
                    visible: parent.hovered
                }
            }
        }

        // 文本内容（展开时显示）
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root._expanded && root.content.length > 0 ? Math.min(textContentText.implicitHeight + 16, 250) : 0
            color: Theme.currentTheme.colors.subtleColor
            radius: 4
            visible: root._expanded && root.content.length > 0
            clip: true

            Flickable {
                anchors.fill: parent
                anchors.margins: 8
                contentWidth: width
                contentHeight: textContentText.implicitHeight
                clip: true

                Text {
                    id: textContentText
                    width: parent.width
                    typography: Typography.Body
                    text: root.content
                    wrapMode: Text.Wrap
                }

                QQC.ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }
        }

        // 提示文字（折叠时显示）
        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: 20
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("点击展开查看全文")
            visible: !root._expanded && root.content.length > 0
            verticalAlignment: Text.AlignVCenter
        }
    }

    // 复制成功提示
    Rectangle {
        id: copyToast
        anchors.centerIn: parent
        width: copyToastText.implicitWidth + 32
        height: 36
        radius: 8
        color: Theme.currentTheme.colors.systemSuccessBackgroundColor
        border.color: Theme.currentTheme.colors.systemSuccessColor
        visible: false
        opacity: visible ? 1 : 0
        z: 10

        Text {
            id: copyToastText
            anchors.centerIn: parent
            typography: Typography.Body
            color: Theme.currentTheme.colors.systemSuccessColor
            text: qsTr("已复制到剪贴板")
        }

        Timer {
            id: copyToastTimer
            interval: 2000
            onTriggered: copyToast.visible = false
        }

        function show() {
            visible = true
            copyToastTimer.restart()
        }
    }
}
