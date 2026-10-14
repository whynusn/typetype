import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../components"

// 晴发文设置区块：服务地址与登录、载文参数（字数/难度/分类/换段模式/精确长度），
// 以及登录对话框与手动换段说明对话框。syncingWenlaiControls 锁 + syncXxxModel
// 填充 + 选中回写模式自洽于本组件，主页不含任何晴发文状态。
ColumnLayout {
    spacing: 4

    property int selectedWenlaiDifficultyLevel: appBridge ? appBridge.wenlaiDifficultyLevel : 0
    property string selectedWenlaiCategory: appBridge ? appBridge.wenlaiCategory : ""
    property string lastWenlaiSegmentMode: appBridge ? appBridge.wenlaiSegmentMode : "manual"
    property bool syncingWenlaiControls: false

    ListModel {
        id: wenlaiDifficultyModel
    }

    ListModel {
        id: wenlaiCategoryModel
    }

    function syncWenlaiDifficultyModel(items) {
        syncingWenlaiControls = true
        wenlaiDifficultyModel.clear()
        var totalCount = 0
        var hasStats = items && items.length > 0
        if (items) {
            for (var i = 0; i < items.length; i++) {
                totalCount += items[i].count || 0
            }
        }
        wenlaiDifficultyModel.append({
            idValue: 0,
            name: hasStats ? qsTr("随机") + " (" + totalCount + qsTr("段") + ")" : qsTr("随机")
        })
        if (items) {
            for (var k = 0; k < items.length; k++) {
                var count = items[k].count || 0
                var label = items[k].name || ""
                if (items[k].count !== undefined && items[k].count !== null)
                    label = label + " (" + count + qsTr("段") + ")"
                wenlaiDifficultyModel.append({
                    idValue: items[k].id || 0,
                    name: label
                })
            }
        }
        var selectedIndex = 0
        for (var j = 0; j < wenlaiDifficultyModel.count; j++) {
            if (wenlaiDifficultyModel.get(j).idValue === selectedWenlaiDifficultyLevel) {
                selectedIndex = j
                break
            }
        }
        wenlaiDifficultyCombo.currentIndex = selectedIndex
        syncingWenlaiControls = false
    }

    function syncWenlaiCategoryModel(items) {
        syncingWenlaiControls = true
        wenlaiCategoryModel.clear()
        wenlaiCategoryModel.append({ codeValue: "", name: qsTr("全部") })
        if (items) {
            for (var i = 0; i < items.length; i++) {
                wenlaiCategoryModel.append({
                    codeValue: items[i].code || "",
                    name: items[i].name || items[i].code || ""
                })
            }
        }
        var selectedIndex = 0
        for (var j = 0; j < wenlaiCategoryModel.count; j++) {
            if (wenlaiCategoryModel.get(j).codeValue === selectedWenlaiCategory) {
                selectedIndex = j
                break
            }
        }
        wenlaiCategoryCombo.currentIndex = selectedIndex
        syncingWenlaiControls = false
    }

    function applyWenlaiConfig() {
        if (!appBridge || syncingWenlaiControls)
            return
        var lengthText = wenlaiLengthField.text.trim()
        var lengthValue = lengthText.length === 0 ? 0 : parseInt(lengthText)
        if (!Number.isInteger(lengthValue) || lengthValue < 0)
            lengthValue = 0
        appBridge.updateWenlaiConfig(
            wenlaiBaseUrlField.text.trim(),
            lengthValue,
            selectedWenlaiDifficultyLevel,
            selectedWenlaiCategory,
            wenlaiAutoSegmentSwitch.checked ? "auto" : "manual",
            wenlaiStrictLengthSwitch.checked
        )
    }

    Component.onCompleted: {
        syncWenlaiDifficultyModel([])
        syncWenlaiCategoryModel([])
        if (appBridge && appBridge.wenlaiLoggedIn) {
            appBridge.refreshWenlaiDifficulties()
            appBridge.refreshWenlaiCategories()
        }
    }

    SettingSectionHeader {
        text: qsTr("晴发文")
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("晴发文服务")
        icon.name: "ic_fluent_cloud_20_regular"
        description: appBridge && appBridge.wenlaiLoggedIn
            ? qsTr("已登录：") + appBridge.wenlaiCurrentUser
            : qsTr("未登录")

        RowLayout {
            spacing: 8

            TextField {
                id: wenlaiBaseUrlField
                implicitWidth: 260
                text: appBridge ? appBridge.wenlaiBaseUrl : "https://qingfawen.fcxxz.com"
                placeholderText: "https://qingfawen.fcxxz.com"
                onAccepted: applyWenlaiConfig()
            }

            Button {
                text: qsTr("应用")
                onClicked: applyWenlaiConfig()
            }

            Button {
                text: appBridge && appBridge.wenlaiLoggedIn ? qsTr("退出") : qsTr("登录")
                highlighted: !(appBridge && appBridge.wenlaiLoggedIn)
                onClicked: {
                    if (!appBridge)
                        return
                    if (appBridge.wenlaiLoggedIn) {
                        appBridge.logoutWenlai()
                    } else {
                        wenlaiLoginDialog.open()
                    }
                }
            }
        }
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("晴发文载文")
        icon.name: "ic_fluent_document_text_20_regular"
        description: qsTr("字数、难度、分类和换段模式")

        RowLayout {
            spacing: 8

            TextField {
                id: wenlaiLengthField
                implicitWidth: 90
                text: appBridge && appBridge.wenlaiLength > 0 ? String(appBridge.wenlaiLength) : ""
                placeholderText: qsTr("不限制")
                onAccepted: applyWenlaiConfig()
            }

            ComboBox {
                id: wenlaiDifficultyCombo
                implicitWidth: 130
                model: wenlaiDifficultyModel
                textRole: "name"
                onCurrentIndexChanged: {
                    if (currentIndex >= 0 && currentIndex < wenlaiDifficultyModel.count) {
                        selectedWenlaiDifficultyLevel = wenlaiDifficultyModel.get(currentIndex).idValue
                        applyWenlaiConfig()
                    }
                }
            }

            ComboBox {
                id: wenlaiCategoryCombo
                implicitWidth: 110
                model: wenlaiCategoryModel
                textRole: "name"
                onCurrentIndexChanged: {
                    if (currentIndex >= 0 && currentIndex < wenlaiCategoryModel.count) {
                        selectedWenlaiCategory = wenlaiCategoryModel.get(currentIndex).codeValue
                        applyWenlaiConfig()
                    }
                }
            }

            Text {
                typography: Typography.Caption
                text: qsTr("自动换段")
            }

            Switch {
                id: wenlaiAutoSegmentSwitch
                checked: appBridge ? appBridge.wenlaiSegmentMode === "auto" : false
                onCheckedChanged: {
                    var nextMode = checked ? "auto" : "manual"
                    if (!syncingWenlaiControls && nextMode === "manual" && lastWenlaiSegmentMode !== "manual") {
                        wenlaiManualModeDialog.open()
                    }
                    applyWenlaiConfig()
                    if (!syncingWenlaiControls) {
                        lastWenlaiSegmentMode = nextMode
                    }
                }
            }

            Text {
                typography: Typography.Caption
                text: qsTr("精确")
            }

            Switch {
                id: wenlaiStrictLengthSwitch
                checked: appBridge ? appBridge.wenlaiStrictLength : false
                onCheckedChanged: applyWenlaiConfig()
            }
        }
    }

    Dialog {
        id: wenlaiManualModeDialog
        title: qsTr("晴发文换段模式")
        modal: true
        standardButtons: Dialog.Ok

        Text {
            width: 300
            text: qsTr("手动换段模式：\n\n打完后不会自动发下一段\n需要按 Ctrl+P 发下一段\n或按 Ctrl+O 发上一段\n按 Ctrl+R 继续随机一段")
            wrapMode: Text.WordWrap
            lineHeight: 1.15
        }
    }

    Dialog {
        id: wenlaiLoginDialog
        title: qsTr("晴发文登录")
        modal: true

        ColumnLayout {
            width: 300
            spacing: 12

            TextField {
                id: wenlaiUsernameField
                placeholderText: qsTr("用户名")
                Layout.fillWidth: true
            }

            TextField {
                id: wenlaiPasswordField
                placeholderText: qsTr("密码")
                echoMode: TextInput.Password
                Layout.fillWidth: true
            }

            Text {
                Layout.fillWidth: true
                horizontalAlignment: Qt.AlignCenter
                typography: Typography.Body
                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#666"
                text: qsTr("没有账号？请先在<a href='https://github.com/a810439322/TypeSunny'>「晴跟打」</a>注册")
                onLinkActivated: function(link) { Qt.openUrlExternally(link) }
            }

            Text {
                id: wenlaiLoginErrorText
                visible: false
                color: Theme.currentTheme.colors.systemCriticalColor
                typography: Typography.Caption
                Layout.fillWidth: true
                horizontalAlignment: Qt.AlignCenter
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: qsTr("取消")
                    Layout.fillWidth: true
                    onClicked: wenlaiLoginDialog.close()
                }

                Button {
                    id: wenlaiLoginButton
                    text: qsTr("登录")
                    highlighted: true
                    Layout.fillWidth: true
                    onClicked: {
                        var username = wenlaiUsernameField.text.trim()
                        var password = wenlaiPasswordField.text
                        if (!username || !password) {
                            wenlaiLoginErrorText.text = qsTr("请输入用户名和密码")
                            wenlaiLoginErrorText.visible = true
                            return
                        }
                        wenlaiLoginErrorText.visible = false
                        wenlaiLoginButton.enabled = false
                        appBridge.loginWenlai(username, password)
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onWenlaiLoginResult(success, message) {
            wenlaiLoginButton.enabled = true
            if (success) {
                wenlaiLoginDialog.close()
            } else {
                wenlaiLoginErrorText.text = message
                wenlaiLoginErrorText.visible = true
            }
        }

        function onWenlaiDifficultiesLoaded(items) {
            syncWenlaiDifficultyModel(items)
        }

        function onWenlaiCategoriesLoaded(items) {
            syncWenlaiCategoryModel(items)
        }

        function onWenlaiConfigChanged() {
            syncingWenlaiControls = true
            wenlaiBaseUrlField.text = appBridge.wenlaiBaseUrl
            wenlaiLengthField.text = appBridge.wenlaiLength > 0 ? String(appBridge.wenlaiLength) : ""
            selectedWenlaiDifficultyLevel = appBridge.wenlaiDifficultyLevel
            selectedWenlaiCategory = appBridge.wenlaiCategory
            wenlaiAutoSegmentSwitch.checked = appBridge.wenlaiSegmentMode === "auto"
            lastWenlaiSegmentMode = appBridge.wenlaiSegmentMode
            wenlaiStrictLengthSwitch.checked = appBridge.wenlaiStrictLength
            syncingWenlaiControls = false
        }
    }
}
