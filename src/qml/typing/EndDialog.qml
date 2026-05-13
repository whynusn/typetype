import QtQuick.Controls 2.15 as QQC
import RinUI
import "../components"

Dialog {
    id: root
    property string scoreMessage: ""
    property bool isSliceAggregate: false

    modal: true
    title: isSliceAggregate ? "打字结束 — 综合成绩" : "打字结束"
    standardButtons: Dialog.Ok

    AppText {
        text: {
            if (isSliceAggregate) {
                return "<b>分片跟打结束，综合成绩已复制</b><br>" + root.scoreMessage;
            }
            return "<b>本次跟打结束，成绩已复制</b><br>" + root.scoreMessage;
        }
        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#2c3e50"
        leftPadding: 20
        rightPadding: 20
    }

    function copyScoreMessage() {
        if (!appBridge) {
            return;
        }
        if (isSliceAggregate) {
            appBridge.copyAggregateScore();
        } else {
            appBridge.copyScoreMessage();
        }
    }

    onAccepted: {
        copyScoreMessage();
    }
}
