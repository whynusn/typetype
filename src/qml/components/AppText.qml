import QtQuick
import RinUI

Text {
    id: root

    property alias fontSize: root.font.pixelSize  // 暴露字体大小属性

    // 默认颜色跟随 RinUI 主题
    color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "black"

    // 默认字体大小（UI 字体由 app.setFont() 全局设定，无需指定 family）
    font.pixelSize: 16
}
