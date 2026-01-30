import QtQuick

Text {
    id: root

    property alias fontSize: root.font.pixelSize  // 暴露字体大小属性
    property alias fontFamily: root.font.family

    // 默认颜色跟随系统调色板
    color: Window.window ? Window.window.palette.text : "black"

    // 可以在这里定义全局的字体大小、字重等
    font.pixelSize: 16
}
