import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    title: qsTr("设置")
    contentSpacing: 4

    Text {
        typography: Typography.Subtitle
        text: qsTr("外观")
        Layout.bottomMargin: 8
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("主题模式")
        icon.name: "ic_fluent_dark_theme_20_regular"
        description: qsTr("在亮色和暗色主题之间切换，或跟随系统设置")

        ComboBox {
            id: themeComboBox
            model: [qsTr("亮色"), qsTr("暗色"), qsTr("跟随系统")]
            currentIndex: {
                var themeName = Theme.getTheme()
                if (themeName === "Light") return 0
                if (themeName === "Dark") return 1
                if (themeName === "Auto") return 2
                return 0
            }
            onCurrentIndexChanged: {
                var modes = ["Light", "Dark", "Auto"]
                var selected = modes[currentIndex]
                if (Theme.getTheme() !== selected) {
                    Theme.setTheme(selected)
                }
            }
        }
    }

    Text {
        typography: Typography.Subtitle
        text: qsTr("网络")
        Layout.topMargin: 16
        Layout.bottomMargin: 8
    }

    SettingCard {
        id: baseUrlCard
        Layout.fillWidth: true
        title: qsTr("服务地址")
        icon.name: "ic_fluent_server_20_regular"
        description: qsTr("API 服务器地址，修改后立即生效并保存到配置文件")

        RowLayout {
            spacing: 8

            TextField {
                id: baseUrlField
                implicitWidth: 260
                text: appBridge ? appBridge.baseUrl : ""
                placeholderText: "http://127.0.0.1:8080"
                onAccepted: {
                    if (text.trim().length > 0) {
                        appBridge.setBaseUrl(text.trim())
                    }
                }
            }

            Button {
                text: qsTr("应用")
                highlighted: true
                onClicked: {
                    if (baseUrlField.text.trim().length > 0) {
                        appBridge.setBaseUrl(baseUrlField.text.trim())
                    }
                }
            }
        }
    }
}
