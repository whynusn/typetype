import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

// 设置页区块标题：Subtitle 字级 + 主题文字色 + 统一上下间距。
// 用法：SettingSectionHeader { text: qsTr("外观") }
Text {
    typography: Typography.Subtitle
    color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : Utils.fallbackTextColor
    Layout.topMargin: 16
    Layout.bottomMargin: 8
}
