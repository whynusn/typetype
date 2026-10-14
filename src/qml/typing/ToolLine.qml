// qml/ToolLine.qml
import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import RinUI

QQC.Pane {
    id: root
    property bool wenlaiLoading: false
    property bool aiTextLoading: false

    padding: 8

    signal requestLoadTextFromClipboard // 定义从剪贴板载文信号
    signal requestLoadWenlai
    signal requestAiText
    signal requestRetype
    signal requestShuffle
    signal requestOpenSliceConfig // 打开载文设置 Dialog
    signal requestSendText // 发文：复制文本段+元数据到剪贴板

    // 自定义 Pane 的背景（跟随 RinUI 主题）
    background: Rectangle {
        color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : Utils.fallbackSurfaceColor
        radius: Utils.radiusSmall
        border.color: Theme.currentTheme ? Theme.currentTheme.colors.controlBorderColor : Utils.fallbackSecondaryTextColor
        border.width: 1
    }

    implicitHeight: flowLayout.childrenRect.height + padding * 2

    Flow {
        id: flowLayout
        anchors.fill: parent
        anchors.leftMargin: 15
        anchors.rightMargin: 15
        anchors.topMargin: 8
        anchors.bottomMargin: 8
        spacing: 8

        Image {
            source: resourceBaseUrl + "images/TypeTypeLogo.png"
            sourceSize: Qt.size(72, 72)
            width: 36
            height: 36
            fillMode: Image.PreserveAspectFit
        }

        // 发文（移到第一位）
        Button {
            id: sendText
            width: Math.max(implicitWidth, 104)
            height: 36
            text: qsTr("发文[C^D]")
            onClicked: {
                root.requestSendText();
            }
        }

        Button {
            id: clipboardLoadText
            width: Math.max(implicitWidth, 104)
            height: 36
            text: qsTr("剪贴板[C^V]")
            onClicked: {
                root.requestLoadTextFromClipboard();
            }
        }

        Button {
            id: retype
            width: Math.max(implicitWidth, 104)
            height: 36
            text: qsTr("重打[F3]")
            onClicked: {
                root.requestRetype();
            }
        }

        Button {
            id: shuffle
            width: Math.max(implicitWidth, 104)
            height: 36
            text: qsTr("乱序[C^L]")
            onClicked: {
                root.requestShuffle();
            }
        }

        // 晴发文
        Button {
            id: wenlaiLoadText
            width: Math.max(implicitWidth, 104)
            height: 36
            enabled: !root.wenlaiLoading
            text: "晴发文[C^R]"
            onClicked: {
                root.requestLoadWenlai();
            }
        }

        Item {
            width: 24
            height: 36

            BusyIndicator {
                anchors.centerIn: parent
                width: 24
                height: 24
                running: root.wenlaiLoading
                visible: root.wenlaiLoading
            }
        }

        // AI 推荐
        Button {
            id: aiRecommend
            width: Math.max(implicitWidth, 104)
            height: 36
            enabled: !root.aiTextLoading
            text: "AI 推荐[^E]"
            onClicked: {
                root.requestAiText();
            }
        }

        Item {
            width: 24
            height: 36
            BusyIndicator {
                anchors.centerIn: parent
                width: 24
                height: 24
                running: root.aiTextLoading
                visible: root.aiTextLoading
            }
        }
    }
}
