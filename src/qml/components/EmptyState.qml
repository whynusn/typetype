import QtQuick 2.15
import RinUI

// 空态占位文本：居中、次级颜色。文案经 text 传入，字级默认 Caption，
// 需要更醒目时由调用方覆盖为 Typography.Body；可见性条件与布局参数保留在调用方。
Text {
    typography: Typography.Caption
    color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : Utils.fallbackSecondaryTextColor
    horizontalAlignment: Text.AlignHCenter
}
