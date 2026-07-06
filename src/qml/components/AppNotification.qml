import QtQuick 2.15
import RinUI

/**
 * 全局通知项。
 *
 * 基于 RinUI InfoBar 封装，支持自动关闭与手动关闭。
 * 由 AppNotificationManager 动态创建，关闭后自动销毁。
 */
InfoBar {
    id: root

    property int duration: 2500  // 自动关闭时间(ms)，-1 表示不自动关闭

    timeout: duration
    position: Position.Top
    isDynamic: true
    closable: true
}
