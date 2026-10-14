// qml/ScoreArea.qml
import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

QQC.Pane {
    id: root

    padding: 0

    background: Rectangle {
        color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : Utils.fallbackSurfaceColor
        // 仅上下边线，作为区块分隔
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : Utils.fallbackSecondaryTextColor
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.currentTheme ? Theme.currentTheme.colors.dividerBorderColor : Utils.fallbackSecondaryTextColor
        }
    }

    RowLayout {
        id: rowLayout
        anchors.fill: parent
        anchors.leftMargin: 20

        PillButton {
            id: typeSpeed
            text: qsTr("速度: %1").arg(appBridge ? appBridge.typeSpeed.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyStroke
            text: qsTr("击键: %1").arg(appBridge ? appBridge.keyStroke.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: codeLength
            text: qsTr("码长: %1").arg(appBridge ? appBridge.codeLength.toFixed(2) : "0.00")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: keyAccuracy
            text: qsTr("键准: %1").arg(appBridge ? appBridge.keyAccuracy.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: charNum
            text: qsTr("字数: %1").arg(appBridge ? appBridge.charNum : 0)
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
        PillButton {
            id: totalTime
            text: qsTr("用时: %1").arg(appBridge ? appBridge.totalTime.toFixed(1) : "0.0")
            checked: true
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
