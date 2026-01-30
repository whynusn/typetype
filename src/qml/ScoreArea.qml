// qml/ScoreArea.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property alias bridge: rowLayout.bridge
    property alias fontSize: rowLayout.fontSize
    property alias fontFamily: rowLayout.fontFamily


    Rectangle {
        z: -1                 // 确保它在内容的下面（避免遮挡）
        radius: 10
        anchors.fill: parent
        anchors.left: parent.left
        anchors.leftMargin: 20   // 距离父容器左边 20px
        anchors.right: parent.right
        anchors.rightMargin: 20  // 距离父容器右边 20px
        color: "lightgray"

        RowLayout {
            id: rowLayout
            anchors {
                fill: parent
                leftMargin: 20   // 相当于 padding-left
                rightMargin: 20  // 相当于 padding-right
            }
            property int fontSize: 14
            property string fontFamily: ""

            property var bridge: null  // 将外部 Bridge 传进来使用（可选）

            /*
        AppText {
            id: usrName
            fontSize: rowLayout.fontSize
            text: "用户: " + "三分月流光"
        }
         */

            AppText {
                id: totalTime
                fontSize: rowLayout.fontSize
                fontFamily: rowLayout.fontFamily
                text: "时间: " + rowLayout.bridge.totalTime.toFixed(1)
            }
            AppText {
                id: typeSpeed
                fontSize: rowLayout.fontSize
                fontFamily: rowLayout.fontFamily
                text: "速度: " + rowLayout.bridge.typeSpeed.toFixed(2)
            }
            AppText {
                id: keyStroke
                fontSize: rowLayout.fontSize
                fontFamily: rowLayout.fontFamily
                text: "击键: " + rowLayout.bridge.keyStroke.toFixed(2)
            }
            AppText {
                id: codeLength
                fontSize: rowLayout.fontSize
                fontFamily: rowLayout.fontFamily
                text: "码长: " + rowLayout.bridge.codeLength.toFixed(2)
            }
            AppText {
                id: charNum
                fontSize: rowLayout.fontSize
                fontFamily: rowLayout.fontFamily
                text: "字数: " + rowLayout.bridge.charNum
            }
        }
    }
}
