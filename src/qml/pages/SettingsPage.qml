import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    title: qsTr("设置")
    contentSpacing: 4

    property int selectedWenlaiDifficultyLevel: appBridge ? appBridge.wenlaiDifficultyLevel : 0
    property string selectedWenlaiCategory: appBridge ? appBridge.wenlaiCategory : ""
    property string lastWenlaiSegmentMode: appBridge ? appBridge.wenlaiSegmentMode : "manual"
    property bool syncingWenlaiControls: false
    property bool syncingZitiControls: false
    property bool _populatingDeviceList: false

    ListModel {
        id: wenlaiDifficultyModel
    }

    ListModel {
        id: wenlaiCategoryModel
    }

    ListModel {
        id: zitiSchemeModel
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
            wenlaiSegmentModeCombo.currentIndex === 1 ? "auto" : "manual",
            wenlaiStrictLengthSwitch.checked
        )
    }

    function syncZitiSchemeModel(items) {
        syncingZitiControls = true
        zitiSchemeModel.clear()
        if (items) {
            for (var i = 0; i < items.length; i++) {
                var count = items[i].entryCount || 0
                var label = items[i].name || ""
                if (count > 0)
                    label = label + " (" + count + qsTr("字") + ")"
                zitiSchemeModel.append({
                    nameValue: items[i].name || "",
                    label: label
                })
            }
        }
        var selectedIndex = -1
        for (var j = 0; j < zitiSchemeModel.count; j++) {
            if (zitiSchemeModel.get(j).nameValue === appBridge.zitiCurrentScheme) {
                selectedIndex = j
                break
            }
        }
        zitiSchemeCombo.currentIndex = selectedIndex
        syncingZitiControls = false
    }

    function _deviceTypeLabel(type) {
        var labels = {
            "keyboard": qsTr("键盘"),
            "mouse": qsTr("鼠标"),
            "touchpad/gamepad": qsTr("触摸板/手柄"),
            "non-keyboard": qsTr("非键盘"),
            "ambiguous": qsTr("类型不明"),
            "unknown": qsTr("未知"),
        }
        return labels[type] || type
    }

    function _refreshDeviceList() {
        _populatingDeviceList = true
        deviceListModel.clear()
        if (!appBridge) {
            _populatingDeviceList = false
            return
        }
        var devices = appBridge.listAvailableInputDevices()
        if (!devices || devices.length === 0) {
            deviceStatusText.text = qsTr("未发现输入设备")
            deviceStatusText.visible = true
            _populatingDeviceList = false
            return
        }
        // 排序：活动设备 → 键盘 → 其他
        devices.sort(function(a, b) {
            if (a.active !== b.active) return a.active ? -1 : 1
            if (a.is_keyboard !== b.is_keyboard) return a.is_keyboard ? -1 : 1
            return 0
        })
        for (var i = 0; i < devices.length; i++) {
            deviceListModel.append({
                path: devices[i].path,
                name: devices[i].name,
                type: devices[i].type,
                is_keyboard: devices[i].is_keyboard,
                selected: devices[i].selected || false,
                active: devices[i].active || false,
            })
        }
        deviceStatusText.visible = false
        _populatingDeviceList = false
    }

    function _applyDeviceSelection() {
        var paths = []
        for (var i = 0; i < deviceListModel.count; i++) {
            if (deviceListModel.get(i).selected) {
                paths.push(deviceListModel.get(i).path)
            }
        }
        if (!appBridge)
            return
        if (paths.length > 0) {
            appBridge.setKeyboardDevices(paths)
        } else {
            appBridge.resetKeyboardAutoDetect()
        }
        deviceStatusText.text = qsTr("已应用")
        deviceStatusText.visible = true
        _showTemporaryStatus()
    }

    function _showTemporaryStatus() {
        var timer = Qt.createQmlObject(
            "import QtQuick 2.15; Timer { interval: 3000; running: true; }",
            this
        )
        timer.triggered.connect(function() {
            deviceStatusText.visible = false
            timer.destroy()
        })
    }

    Component.onCompleted: {
        syncWenlaiDifficultyModel([])
        syncWenlaiCategoryModel([])
        if (appBridge && appBridge.wenlaiLoggedIn) {
            appBridge.refreshWenlaiDifficulties()
            appBridge.refreshWenlaiCategories()
        }
        if (appBridge)
            appBridge.loadZitiSchemes()
        // 延迟加载键盘设备列表，避免 evdev 扫描阻塞首次页面渲染
        Qt.callLater(_refreshDeviceList)
    }

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

    Text {
        typography: Typography.Subtitle
        text: qsTr("晴发文")
        Layout.topMargin: 16
        Layout.bottomMargin: 8
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

            ComboBox {
                id: wenlaiSegmentModeCombo
                implicitWidth: 90
                model: [qsTr("手动"), qsTr("自动")]
                Component.onCompleted: {
                    currentIndex = appBridge && appBridge.wenlaiSegmentMode === "auto" ? 1 : 0
                }
                onCurrentIndexChanged: {
                    var nextMode = currentIndex === 1 ? "auto" : "manual"
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

    Text {
        typography: Typography.Subtitle
        text: qsTr("字提示")
        Layout.topMargin: 16
        Layout.bottomMargin: 8
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("字提示方案")
        icon.name: "ic_fluent_text_grammar_wand_20_regular"
        description: appBridge && appBridge.zitiLoadedCount > 0
            ? appBridge.zitiCurrentScheme + qsTr("，") + appBridge.zitiLoadedCount + qsTr(" 字")
            : qsTr("在跟打页显示当前字的编码提示")

        RowLayout {
            spacing: 8

            Switch {
                id: zitiEnabledSwitch
                checked: appBridge ? appBridge.zitiEnabled : false
                onCheckedChanged: {
                    if (appBridge && !syncingZitiControls)
                        appBridge.setZitiEnabled(checked)
                }
            }

            ComboBox {
                id: zitiSchemeCombo
                implicitWidth: 180
                model: zitiSchemeModel
                textRole: "label"
                onCurrentIndexChanged: {
                    if (!appBridge || syncingZitiControls)
                        return
                    if (currentIndex >= 0 && currentIndex < zitiSchemeModel.count) {
                        appBridge.loadZitiScheme(zitiSchemeModel.get(currentIndex).nameValue)
                    }
                }
            }

            Button {
                text: qsTr("刷新")
                onClicked: {
                    if (appBridge)
                        appBridge.loadZitiSchemes()
                }
            }
        }
    }

    Text {
        typography: Typography.Subtitle
        text: qsTr("键盘设备")
        Layout.topMargin: 16
        Layout.bottomMargin: 8
    }

    SettingCard {
        id: keyboardDeviceCard
        Layout.fillWidth: true
        title: appBridge && appBridge.hasManualKeyboardDevices
            ? qsTr("键盘设备（手动选择）")
            : qsTr("键盘设备（自动发现）")
        icon.name: "ic_fluent_keyboard_20_regular"
        description: qsTr("勾选要监听的输入设备")

        RowLayout {
            spacing: 6

            Button {
                text: qsTr("刷新")
                onClicked: {
                    if (appBridge)
                        appBridge.refreshInputDevices()
                }
            }

            Button {
                text: qsTr("恢复自动发现")
                enabled: appBridge && appBridge.hasManualKeyboardDevices
                onClicked: {
                    if (appBridge)
                        appBridge.resetKeyboardAutoDetect()
                }
            }

            Text {
                id: deviceStatusText
                typography: Typography.Caption
                visible: false
            }
        }
    }

    Frame {
        Layout.fillWidth: true
        leftPadding: 15
        rightPadding: 15
        topPadding: 8
        bottomPadding: 8
        visible: deviceListModel.count > 0

        ColumnLayout {
            anchors.fill: parent
            spacing: 4

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(deviceListModel.count * 32 + 4, 160)
                clip: true

                ColumnLayout {
                    spacing: 1
                    width: parent.width

                    Repeater {
                        id: deviceRepeater
                        model: ListModel { id: deviceListModel }

                        delegate: Rectangle {
                            id: deviceRow
                            Layout.fillWidth: true
                            Layout.preferredHeight: 30
                            color: model.active
                                ? Theme.currentTheme.colors.cardColor
                                : "transparent"
                            radius: 4

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 2
                                anchors.rightMargin: 4
                                spacing: 6

                                CheckBox {
                                    id: deviceCheck
                                    checked: model.selected
                                    implicitHeight: 20
                                    implicitWidth: 20
                                    padding: 0
                                    onCheckedChanged: {
                                        if (_populatingDeviceList)
                                            return
                                        deviceListModel.setProperty(index, "selected", checked)
                                        _applyDeviceSelection()
                                    }
                                }

                                Rectangle {
                                    id: activeDot
                                    width: 6
                                    height: 6
                                    radius: 3
                                    visible: model.active
                                    color: Theme.currentTheme.colors.systemSuccessColor
                                }

                                Text {
                                    text: model.name
                                    typography: Typography.Body
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    opacity: model.active ? 1.0 : 0.6
                                }

                                Text {
                                    text: model.active
                                        ? qsTr("活动中")
                                        : _deviceTypeLabel(model.type)
                                    typography: Typography.Caption
                                    opacity: model.active ? 1.0 : 0.5
                                }
                            }
                        }
                    }
                }
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
            wenlaiSegmentModeCombo.currentIndex = appBridge.wenlaiSegmentMode === "auto" ? 1 : 0
            lastWenlaiSegmentMode = appBridge.wenlaiSegmentMode
            wenlaiStrictLengthSwitch.checked = appBridge.wenlaiStrictLength
            syncingWenlaiControls = false
        }

        function onZitiSchemesLoaded(items) {
            syncZitiSchemeModel(items)
        }

        function onZitiStateChanged() {
            syncingZitiControls = true
            zitiEnabledSwitch.checked = appBridge.zitiEnabled
            syncingZitiControls = false
        }

        function onKeyboardDevicesChanged() {
            _refreshDeviceList()
        }
    }
}
