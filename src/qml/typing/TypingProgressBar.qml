// TypingProgressBar.qml — 简洁的打字进度条（参考 RinUI 风格）
import QtQuick 2.15
import RinUI

Rectangle {
    id: root
    property real progress: 0.0   // 0.0 ~ 1.0

    height: 3
    radius: 99
    color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : "#e0e0e0"
    clip: true

    Rectangle {
        id: indicator
        height: parent.height
        radius: parent.radius
        color: Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#4b88ff"
        width: root.progress * root.width
        opacity: 0.85

        Behavior on width {
            NumberAnimation {
                duration: 120
                easing.type: Easing.OutCubic
            }
        }
    }
}
