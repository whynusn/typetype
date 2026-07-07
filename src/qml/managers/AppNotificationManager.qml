import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

/**
 * 全局通知管理器。
 *
 * 用法：
 *   Window.window.appNotificationManager.show(Severity.Success, "标题", "消息", 2000)
 *
 * 通知会堆叠显示在窗口顶部中央，自动关闭后销毁。
 * 同时显示的通知数受 maxVisible 限制，超出部分进入队列。
 */
ColumnLayout {
    id: root

    property int maxVisible: 3

    spacing: 8

    QtObject {
        id: internal
        property var active: []
        property var pending: []
    }

    function show(severity, title, message, duration) {
        var data = {
            severity: severity,
            title: title,
            message: message,
            duration: duration
        }
        if (internal.active.length < maxVisible) {
            createNotification(data)
        } else {
            internal.pending.push(data)
        }
    }

    function createNotification(data) {
        var comp = Qt.createComponent("../components/AppNotification.qml")
        if (comp.status !== Component.Ready) {
            console.error("[AppNotificationManager] Failed to create AppNotification:", comp.errorString())
            return
        }
        var obj = comp.createObject(root, {
            severity: data.severity,
            title: data.title,
            text: data.message,
            duration: data.duration
        })
        if (!obj) {
            console.error("[AppNotificationManager] createObject returned null")
            return
        }
        internal.active.push(obj)
        obj.Component.onDestruction.connect(function() { onNotificationDestroyed(obj) })
    }

    function onNotificationDestroyed(obj) {
        var idx = internal.active.indexOf(obj)
        if (idx >= 0) {
            internal.active.splice(idx, 1)
        }
        if (internal.pending.length > 0) {
            var next = internal.pending.shift()
            createNotification(next)
        }
    }
}
