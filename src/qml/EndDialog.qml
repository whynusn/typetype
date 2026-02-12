import QtQuick.Controls

Dialog {
    id: root
    property alias fontSize: root.font.pixelSize
    property alias fontFamily: root.font.family
    property var bridge: null
    property string scoreMessage: ""

    modal: true
    title: "打字结束"
    standardButtons: Dialog.Ok | Dialog.Cancel

    AppText {
        text: "<b>本次跟打结束，是否复制成绩？</b><br>" + root.scoreMessage
        fontSize: root.fontSize
        fontFamily: root.fontFamily
        color: "#2c3e50"
        leftPadding: 20
        rightPadding: 20
    }

    function copyScoreMessage() {
        if (!root.bridge) {
            return;
        }
        root.bridge.copyScoreMessage();
    }

    onAccepted: {
        copyScoreMessage();
        console.log("Ok clicked");
    }
    onRejected: console.log("Cancel clicked")
}
