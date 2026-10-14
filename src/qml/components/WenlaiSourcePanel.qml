import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

/**
 * 晴发文即时源面板。
 *
 * 公共骨架（居中布局/图标标题/错误行/主操作行/openSettings）由 InstantSourcePanel 承载；
 * 此处保留登录状态行与加载配置摘要卡。状态一律经 appBridge 读取（null 守卫）。
 */
InstantSourcePanel {
    id: root

    icon: "ic_fluent_book_20_regular"
    title: qsTr("晴发文")
    description: qsTr("每次从晴发文随机获取一篇文章，分段连载，即点即打。")
    loading: appBridge ? appBridge.wenlaiLoading : false
    actionText: qsTr("随机一篇")
    actionEnabled: !!appBridge

    // ---- 登录状态行 ----
    RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 32
        spacing: 8

        Text {
            Layout.fillWidth: true
            typography: Typography.Body
            color: Theme.currentTheme.colors.textColor
            text: (appBridge && appBridge.wenlaiLoggedIn)
                  ? qsTr("已登录：%1").arg(appBridge.wenlaiCurrentUser)
                  : qsTr("未登录（部分书库受限）")
            elide: Text.ElideRight
        }

        Button {
            text: (appBridge && appBridge.wenlaiLoggedIn) ? qsTr("账号设置") : qsTr("去登录")
            flat: true
            icon.name: "ic_fluent_settings_20_regular"
            onClicked: root.openSettings()
        }
    }

    // ---- 配置摘要卡 ----
    Frame {
        Layout.fillWidth: true
        radius: 6
        hoverable: false
        padding: 12

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("长度")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.wenlaiLength > 0) ? appBridge.wenlaiLength : qsTr("默认")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("难度")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.wenlaiDifficultyLevel > 0) ? appBridge.wenlaiDifficultyLevel : qsTr("全部")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("分类")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.wenlaiCategory) ? appBridge.wenlaiCategory : qsTr("全部")
                    elide: Text.ElideRight
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("分段模式")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.wenlaiSegmentMode === "auto") ? qsTr("自动分段") : qsTr("手动分段")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: qsTr("修改配置")
                    flat: true
                    icon.name: "ic_fluent_settings_20_regular"
                    onClicked: root.openSettings()
                }
            }
        }
    }
}
