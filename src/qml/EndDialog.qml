import QtQuick.Controls

Dialog {
    id: root
    property alias fontSize: root.font.pixelSize
    property alias fontFamily: root.font.family
    property var bridge: null

    modal: true
    title: "打字结束"
    standardButtons: Dialog.Ok | Dialog.Cancel
    height: 150

    AppText {
        text: "本次跟打结束，是否分享成绩？"
        fontSize: root.fontSize
        fontFamily: root.fontFamily
    }

    onAccepted: console.log("Ok clicked")
    onRejected: console.log("Cancel clicked")
}
