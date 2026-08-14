import QtQuick
import QtQuick.Controls
import "../../themes"
import "../../utils"

Text {
    id: label
    property int typography: -1

    color: targetColor
    linkColor: Theme.currentTheme.colors.primaryColor
    property color targetColor: Theme.currentTheme.colors.textColor  // 目标颜色，用于切换动画
    wrapMode: Text.WordWrap

    // 主题切换动画  TODO: 会坠机
    // Behavior on color {
    //     ColorAnimation {
    //         duration: Utils.appearanceSpeed
    //         easing.type: Easing.OutQuart
    //     }
    // }

    font.pixelSize: {
        switch (typography) {
            case Typography.Display: return Theme.currentTheme.typography.displaySize;
            case Typography.TitleLarge: return Theme.currentTheme.typography.titleLargeSize;
            case Typography.Title: return Theme.currentTheme.typography.titleSize;
            case Typography.Subtitle: return Theme.currentTheme.typography.subtitleSize;
            case Typography.Body: return Theme.currentTheme.typography.bodySize;
            case Typography.BodyStrong: return Theme.currentTheme.typography.bodyStrongSize;
            case Typography.BodyLarge: return Theme.currentTheme.typography.bodyLargeSize;
            case Typography.Caption: return Theme.currentTheme.typography.captionSize;
            default: return Theme.currentTheme.typography.bodySize;
        }
    }

    font.family: Utils.fontFamily

    font.weight: {
        switch (typography) {
            case Typography.Display:
            case Typography.TitleLarge:
            case Typography.Title:
            case Typography.Subtitle:
            case Typography.BodyLarge:
            case Typography.BodyStrong:
                return Font.DemiBold;
            case Typography.Body:
            case Typography.Caption:
                return Font.Normal;
            default:
                return font.weight;
        }
    }
}
