import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../components"

// AI 智能推荐设置区块：API 地址/模型/请求格式、API Key 保存、目标字数。
// syncingAiControls 锁 + onAiConfigChanged 回写模式自洽于本组件。
ColumnLayout {
    spacing: 4

    property bool syncingAiControls: false

    function applyAiConfig() {
        if (!appBridge || syncingAiControls)
            return
        var baseUrl = aiBaseUrlField.text.trim()
        var model = aiModelField.text.trim()
        // 空输入 = 保持当前配置并回显原值（后端空串会产生非法请求 URL
        // 如 "/chat/completions"，不能写空；旧实现静默丢弃用户输入）
        if (baseUrl) {
            appBridge.updateAiBaseUrl(baseUrl)
        } else {
            aiBaseUrlField.text = appBridge.aiBaseUrl
        }
        if (model) {
            appBridge.updateAiModel(model)
        } else {
            aiModelField.text = appBridge.aiModel
        }
    }

    function applyAiMaxChars() {
        if (!appBridge || syncingAiControls)
            return
        var value = parseInt(aiMaxCharsField.text)
        if (Number.isInteger(value) && value >= 50) {
            appBridge.updateAiMaxChars(value)
        }
    }

    SettingSectionHeader {
        text: qsTr("AI 智能推荐")
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("AI 服务配置")
        icon.name: "ic_fluent_lightbulb_20_regular"
        description: qsTr("API 地址、模型和请求格式")

        RowLayout {
            spacing: 8

            TextField {
                id: aiBaseUrlField
                implicitWidth: 220
                text: appBridge ? appBridge.aiBaseUrl : ""
                placeholderText: qsTr("API Base URL")
            }

            TextField {
                id: aiModelField
                implicitWidth: 140
                text: appBridge ? appBridge.aiModel : ""
                placeholderText: qsTr("模型名称")
            }

            ComboBox {
                id: aiApiFormatCombo
                implicitWidth: 160
                model: ListModel {
                    ListElement { name: "Chat Completions"; value: "openai_chat" }
                    ListElement { name: "Responses API"; value: "openai_response" }
                    ListElement { name: "Anthropic"; value: "anthropic" }
                }
                textRole: "name"
                onCurrentIndexChanged: {
                    if (appBridge && !syncingAiControls) {
                        appBridge.updateAiApiFormat(model.get(currentIndex).value)
                    }
                }
            }

            Button {
                text: qsTr("应用")
                onClicked: applyAiConfig()
            }
        }
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("AI API Key")
        icon.name: "ic_fluent_key_20_regular"
        description: appBridge && appBridge.hasAiApiKey
            ? qsTr("已配置")
            : qsTr("未配置")

        RowLayout {
            spacing: 8

            TextField {
                id: aiApiKeyField
                implicitWidth: 300
                placeholderText: qsTr("输入 API Key")
                echoMode: TextInput.Password
            }

            Button {
                text: qsTr("保存")
                highlighted: true
                onClicked: {
                    if (!appBridge) return
                    var key = aiApiKeyField.text.trim()
                    if (!key) return
                    if (appBridge.updateAiApiKey(key)) {
                        aiApiKeyStatus.text = qsTr("已保存")
                        aiApiKeyStatus.color = Theme.currentTheme ? Theme.currentTheme.colors.systemSuccessColor : "#107c10"
                        aiApiKeyField.text = ""
                    } else {
                        aiApiKeyStatus.text = qsTr("保存失败")
                        aiApiKeyStatus.color = Theme.currentTheme ? Theme.currentTheme.colors.systemCriticalColor : "#c42b1c"
                    }
                    aiApiKeyStatus.visible = true
                }
            }

            Text {
                id: aiApiKeyStatus
                visible: false
                typography: Typography.Caption
            }
        }
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("生成参数")
        icon.name: "ic_fluent_options_20_regular"
        description: qsTr("生成文本的目标字数")

        RowLayout {
            spacing: 8

            Text {
                typography: Typography.Caption
                text: qsTr("目标字数")
            }

            TextField {
                id: aiMaxCharsField
                implicitWidth: 80
                text: appBridge ? String(appBridge.aiMaxChars) : "300"
                onAccepted: applyAiMaxChars()
            }

            Button {
                text: qsTr("应用")
                onClicked: applyAiMaxChars()
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onAiConfigChanged() {
            syncingAiControls = true
            aiBaseUrlField.text = appBridge.aiBaseUrl
            aiModelField.text = appBridge.aiModel
            aiMaxCharsField.text = String(appBridge.aiMaxChars)
            var f = appBridge.aiApiFormat
            if (f === "openai_response") aiApiFormatCombo.currentIndex = 1
            else if (f === "anthropic") aiApiFormatCombo.currentIndex = 2
            else aiApiFormatCombo.currentIndex = 0
            syncingAiControls = false
        }
    }
}
