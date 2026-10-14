import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

/**
 * AI 推荐即时源面板。
 *
 * 公共骨架（居中布局/图标标题/错误行/主操作行/openSettings）由 InstantSourcePanel 承载；
 * 此处保留未配置 API Key 的「去配置」引导与已配置时的模型/长度摘要卡。
 * 状态一律经 appBridge 读取（null 守卫）。
 */
InstantSourcePanel {
    id: root

    icon: "ic_fluent_sparkle_20_regular"
    title: qsTr("AI 推荐")
    description: qsTr("由大模型即时生成一篇练习文本。")
    loading: appBridge ? appBridge.aiTextLoading : false
    actionText: qsTr("生成一篇")
    actionEnabled: !!(appBridge && appBridge.hasAiApiKey)
    // 未配置时只展示引导，主操作行整体隐藏（与原「已配置才显示」行为一致）
    actionVisible: !!(appBridge && appBridge.hasAiApiKey)

    // ---- 未配置 API Key：引导去配置 ----
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 10
        visible: !(appBridge && appBridge.hasAiApiKey)

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Body
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("尚未配置 API Key")
            horizontalAlignment: Text.AlignHCenter
        }

        Button {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("去配置")
            highlighted: true
            onClicked: root.openSettings()
        }
    }

    // ---- 已配置：配置摘要卡 ----
    Frame {
        Layout.fillWidth: true
        visible: !!(appBridge && appBridge.hasAiApiKey)
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
                    text: qsTr("模型")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.aiModel) ? appBridge.aiModel : qsTr("默认")
                    elide: Text.ElideRight
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("长度上限")
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: (appBridge && appBridge.aiMaxChars > 0) ? appBridge.aiMaxChars : qsTr("默认")
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
