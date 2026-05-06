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

    ListModel {
        id: readerFontModel
    }

    ListModel {
        id: deviceListModel
    }

    property int _selectedFontIndex: -1

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
    }

    Component.onCompleted: {
        syncWenlaiDifficultyModel([])
        syncWenlaiCategoryModel([])
        if (appBridge && appBridge.wenlaiLoggedIn) {
            appBridge.refreshWenlaiDifficulties()
            appBridge.refreshWenlaiCategories()
        }
        if (appBridge) {
            appBridge.loadZitiSchemes()
            appBridge.loadFonts()
        }
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

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("阅读字体")
        icon.name: "ic_fluent_text_font_20_regular"
        description: qsTr("选择打字练习区域使用的字体，可添加自定义字体文件")

        RowLayout {
            spacing: 8

            Text {
                id: currentFontLabel
                text: {
                    if (_selectedFontIndex >= 0 && _selectedFontIndex < readerFontModel.count) {
                        var item = readerFontModel.get(_selectedFontIndex);
                        return item ? item.label : qsTr("未选择");
                    }
                    return qsTr("未选择");
                }
                typography: Typography.Body
                elide: Text.ElideRight
                Layout.fillWidth: true
                color: Theme.currentTheme.colors.textColor
            }

            Button {
                text: qsTr("管理")
                onClicked: fontManagerDialog.open()
            }
        }

        Connections {
            target: appBridge

            function onFontsLoaded(fonts) {
                readerFontModel.clear();
                var currentPath = appBridge ? appBridge.readerFontPath : "";
                var idx = -1;
                for (var i = 0; i < fonts.length; i++) {
                    var f = fonts[i];
                    readerFontModel.append({
                        label: f.name + (f.isBundled ? qsTr(" (内置)") : ""),
                        name: f.name,
                        filePath: f.filePath,
                        isBundled: f.isBundled
                    });
                    if (f.filePath === currentPath) {
                        idx = i;
                    }
                }
                _selectedFontIndex = idx;
                if (idx < 0 && readerFontModel.count > 0 && currentPath === "") {
                    _selectedFontIndex = 0;
                    if (appBridge) {
                        appBridge.setReaderFontPath(readerFontModel.get(0).filePath);
                    }
                }
            }

            function onFontAdded(success, message) {
                // loadFonts() is already triggered by FontAdapter on success
            }

            function onFontRemoved(success, message) {
                // loadFonts() is already triggered by FontAdapter on success
            }
        }
    }

    Dialog {
        id: fontManagerDialog
        title: qsTr("管理阅读字体")
        modal: true
        standardButtons: Dialog.Close
        width: 420

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 12

            Text {
                text: {
                    if (_selectedFontIndex >= 0 && _selectedFontIndex < readerFontModel.count) {
                        var item = readerFontModel.get(_selectedFontIndex);
                        return item ? qsTr("当前字体：") + item.label : qsTr("当前字体：") + qsTr("未选择");
                    }
                    return qsTr("当前字体：") + qsTr("未选择");
                }
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: Theme.currentTheme.colors.dividerBorderColor
                visible: readerFontModel.count > 0
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(readerFontModel.count * 40 + 4, 280)
                clip: true
                visible: readerFontModel.count > 0

                ColumnLayout {
                    spacing: 2
                    width: parent.width

                    Repeater {
                        model: readerFontModel

                        delegate: Rectangle {
                            id: fontDlgDelegate
                            property int fontIndex: index
                            property string fontName: model.name
                            property string fontFilePath: model.filePath
                            property string fontLabel: model.label
                            property bool fontIsBundled: model.isBundled
                            property bool _highlighted: false
                            property bool _deleting: false

                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            radius: 4
                            color: _highlighted
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : "transparent"

                            Behavior on color { ColorAnimation { duration: Utils.appearanceSpeed; easing.type: Easing.InOutQuart } }

                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    _selectedFontIndex = fontDlgDelegate.fontIndex;
                                    if (appBridge) appBridge.setReaderFontPath(fontDlgDelegate.fontFilePath);
                                }
                                onEntered: fontDlgDelegate._highlighted = true
                                onExited: fontDlgDelegate._highlighted = false
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                Rectangle {
                                    width: 3
                                    height: 14
                                    radius: 10
                                    color: Theme.currentTheme.colors.primaryColor
                                    visible: fontDlgDelegate.fontIndex === _selectedFontIndex
                                }

                                Text {
                                    text: fontDlgDelegate.fontLabel
                                    typography: Typography.Body
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                ToolButton {
                                    flat: true
                                    icon.name: "ic_fluent_delete_20_regular"
                                    visible: !fontDlgDelegate.fontIsBundled
                                    enabled: !fontDlgDelegate._deleting
                                    onClicked: {
                                        if (!appBridge) return;
                                        fontDlgDelegate._deleting = true;
                                        appBridge.removeFont(fontDlgDelegate.fontName);
                                    }
                                    ToolTip.text: qsTr("删除此字体")
                                    ToolTip.visible: hovered
                                }
                            }
                        }
                    }
                }
            }

            Text {
                text: qsTr("暂无字体")
                visible: readerFontModel.count === 0
                horizontalAlignment: Qt.AlignHCenter
                Layout.fillWidth: true
                color: Theme.currentTheme.colors.textSecondaryColor
                typography: Typography.Caption
            }

            Button {
                text: qsTr("添加字体")
                icon.name: "ic_fluent_add_20_regular"
                Layout.alignment: Qt.AlignHCenter
                onClicked: {
                    if (appBridge) appBridge.openFontFileDialog();
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

        Button {
            text: qsTr("管理")
            onClicked: keyboardManagerDialog.open()
        }
    }

    Dialog {
        id: keyboardManagerDialog
        title: qsTr("管理键盘设备")
        modal: true
        width: 420

        contentItem: ColumnLayout {
            spacing: 12

            Text {
                Layout.fillWidth: true
                typography: Typography.Subtitle
                text: keyboardManagerDialog.title
            }

            RowLayout {
                spacing: 8
                Layout.fillWidth: true

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
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(deviceListModel.count * 36 + 4, 240)
                clip: true
                visible: deviceListModel.count > 0

                ColumnLayout {
                    spacing: 2
                    width: parent.width

                    Repeater {
                        model: deviceListModel

                        delegate: Rectangle {
                            id: devDlgDelegate
                            property int devIndex: index
                            property string devPath: model.path
                            property string devName: model.name
                            property string devType: model.type
                            property bool devIsKeyboard: model.is_keyboard
                            property bool devSelected: model.selected
                            property bool devActive: model.active

                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            radius: 4
                            color: devActive
                                ? Theme.currentTheme.colors.cardColor
                                : "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                CheckBox {
                                    checked: devDlgDelegate.devSelected
                                    implicitHeight: 20
                                    implicitWidth: 20
                                    padding: 0
                                    onCheckedChanged: {
                                        if (_populatingDeviceList)
                                            return
                                        deviceListModel.setProperty(devDlgDelegate.devIndex, "selected", checked)
                                        _applyDeviceSelection()
                                    }
                                }

                                Rectangle {
                                    width: 6
                                    height: 6
                                    radius: 3
                                    visible: devDlgDelegate.devActive
                                    color: Theme.currentTheme.colors.systemSuccessColor
                                }

                                Text {
                                    text: devDlgDelegate.devName
                                    typography: Typography.Body
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    opacity: devDlgDelegate.devActive ? 1.0 : 0.6
                                }

                                Text {
                                    text: devDlgDelegate.devActive
                                        ? qsTr("活动中")
                                        : _deviceTypeLabel(devDlgDelegate.devType)
                                    typography: Typography.Caption
                                    opacity: devDlgDelegate.devActive ? 1.0 : 0.5
                                }
                            }
                        }
                    }
                }
            }

            Text {
                text: qsTr("未发现输入设备")
                visible: deviceListModel.count === 0
                horizontalAlignment: Qt.AlignHCenter
                Layout.fillWidth: true
                color: Theme.currentTheme.colors.textSecondaryColor
                typography: Typography.Caption
            }

            Button {
                text: qsTr("关闭")
                Layout.alignment: Qt.AlignRight
                onClicked: keyboardManagerDialog.close()
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
                font.pixelSize: 12
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
