import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

/**
 * AI 推荐即时源面板。
 *
 * 未配置 API Key 时展示「去配置」引导；已配置时展示模型/长度摘要与「生成一篇」主操作。
 * 配置入口跳转设置页；状态一律经 appBridge 读取（null 守卫）。
 */
Frame {
    id: root

    // ---- 输出 ----
    signal loadRequested()  // 「生成一篇」触发（由父级接入 appBridge.requestAiText）

    // 跳转设置页（相对 URL 以本文件位置解析，与 typing/SliceHelpers 惯例一致）
    function openSettings() {
        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("../pages/SettingsPage.qml"))
        }
    }

    Layout.fillWidth: true
    Layout.fillHeight: true
    radius: 6
    hoverable: false

    // ---- 内容（居中，最大宽度 560） ----
    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 32, 560)
        spacing: 12

        IconWidget {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            icon: "ic_fluent_sparkle_20_regular"
            color: Theme.currentTheme.colors.primaryColor
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Subtitle
            color: Theme.currentTheme.colors.textColor
            text: qsTr("AI 推荐")
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("由大模型即时生成一篇练习文本。")
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }

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

        // ---- 已配置：配置摘要 + 主操作 ----
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 12
            visible: appBridge && appBridge.hasAiApiKey

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
                            onClicked: root.openSettings()
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                spacing: 8

                BusyIndicator {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    running: appBridge ? appBridge.aiTextLoading : false
                    visible: running
                }

                Button {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    text: qsTr("生成一篇")
                    highlighted: true
                    enabled: appBridge && appBridge.hasAiApiKey && !appBridge.aiTextLoading
                    onClicked: root.loadRequested()
                }
            }
        }
    }
}
