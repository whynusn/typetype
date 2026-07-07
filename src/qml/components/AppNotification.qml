import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import RinUI

/**
 * 全局通知项。
 *
 * 基于 RinUI InfoBar 封装，支持自动关闭、手动关闭、复制内容。
 * 由 AppNotificationManager 动态创建，关闭后自动销毁。
 *
 * 用法（通过 AppNotificationManager）：
 *   show(Severity.Error, "标题", "消息", -1, { showCopy: true })
 */
InfoBar {
    id: root

    property int duration: 2500  // 自动关闭时间(ms)，-1 表示不自动关闭
    property bool showCopy: false  // 是否显示复制按钮

    timeout: duration
    position: Position.Top
    isDynamic: true
    closable: true

    Button {
        id: copyButton
        visible: root.showCopy
        text: qsTr("复制")
        flat: true
        height: 28
        onClicked: {
            if (root.text) {
                QQC.Clipboard.setText(root.text)
                copyButton.text = qsTr("已复制")
                copyResetTimer.start()
            }
        }
    }

    Timer {
        id: copyResetTimer
        interval: 1600
        onTriggered: {
            copyButton.text = qsTr("复制")
        }
    }
}
