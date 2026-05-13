// qml/ScoreArea.qml
import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

QQC.Pane {
    id: root

    padding: 0

    background: Rectangle {
        color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : "lightgray"
        // 仅上下边线，作为区块分隔
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        }
    }

    RowLayout {
        id: rowLayout
        anchors.fill: parent
        anchors.leftMargin: 20

        PillButton {
            id: typeSpeed
            text: "速度: " + (appBridge ? appBridge.typeSpeed.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyStroke
            text: "击键: " + (appBridge ? appBridge.keyStroke.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: codeLength
            text: "码长: " + (appBridge ? appBridge.codeLength.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyAccuracy
            text: "键准: " + (appBridge ? appBridge.keyAccuracy.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: charNum
            text: "字数: " + (appBridge ? appBridge.charNum : 0)
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: totalTime
            text: "用时: " + (appBridge ? appBridge.totalTime.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
