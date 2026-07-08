import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import RinUI

/**
 * 全局通知项。
 *
 * 基于 RinUI InfoBar 封装，支持自动关闭、手动关闭、复制内容。
 * 由 AppNotificationManager 动态创建，关闭后自动销毁。
 *
 * 复制按钮由 InfoBar 原生支持（rights 区域，图标(左) | 正文 | 复制(右) | 关闭(右)）。
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
    showCopy: root.showCopy
    copyText: root.text
}
