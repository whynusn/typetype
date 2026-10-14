import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../components"
import "../settings"

FluentPage {
    title: qsTr("设置")
    contentSpacing: 4

    // 晴发文 / AI / 键盘设备三个区块已拆到 settings/ 子组件，状态自洽于各自组件；
    // 本页只保留：外观（主题/字体）、网络、字提示、关于与更新。

    property bool syncingZitiControls: false
    property bool updateChecking: false
    property bool updateDownloading: false
    property bool updateAvailable: false
    property string updateVersion: ""
    property string updateErrorText: ""
    property int updateProgress: 0
    // 本次会话内完成过一次手动检查（让「已是最新版本」反馈态可见）
    property bool updateChecked: false

    ListModel {
        id: zitiSchemeModel
    }

    ListModel {
        id: readerFontModel
    }

    property int _selectedFontIndex: -1

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

    Component.onCompleted: {
        if (appBridge) {
            appBridge.loadZitiSchemes()
            appBridge.loadFonts()
        }
    }

    SettingSectionHeader {
        text: qsTr("外观")
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

    FontManagerDialog {
        id: fontManagerDialog
        fontModel: readerFontModel
        selectedFontIndex: _selectedFontIndex
        onFontSelected: function(index, filePath) {
            _selectedFontIndex = index
            if (appBridge) appBridge.setReaderFontPath(filePath)
        }
    }

    SettingSectionHeader {
        text: qsTr("网络")
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("打字历史")
        icon.name: "ic_fluent_history_20_regular"
        description: qsTr("最多保留的历史记录条数，超出后自动截断旧记录")

        RowLayout {
            spacing: 8

            SpinBox {
                id: historyMaxSpinBox
                from: 100
                to: 100000
                stepSize: 1000
                value: appBridge ? appBridge.typingHistoryMaxRecords : 2000
                onValueModified: {
                    if (appBridge) appBridge.setTypingHistoryMaxRecords(value)
                }
            }

            Text {
                text: qsTr("条")
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
            }

            Item { Layout.fillWidth: true }

            Text {
                text: qsTr("当前: %1 条").arg(appBridge ? appBridge.typingHistoryCount : 0)
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
            }
        }
    }

    SettingCard {
        id: registryUrlCard
        Layout.fillWidth: true
        title: qsTr("开源文库")
        icon.name: "ic_fluent_text_bullet_list_20_regular"
        description: qsTr("开源文库远程脚本开关")

        ColumnLayout {
            spacing: 6

            RowLayout {
                spacing: 8

                Text {
                    typography: Typography.Caption
                    text: qsTr("远程脚本")
                    Layout.preferredWidth: 48
                }

                Switch {
                    id: ottScriptsSwitch
                    checked: appBridge ? appBridge.scriptsEnabled : false
                    onCheckedChanged: {
                        if (appBridge) appBridge.setScriptsEnabled(checked)
                    }
                }

                Text {
                    typography: Typography.Caption
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: qsTr("执行开源文库分发的 ott-script 脚本（Windows 默认关闭：沙箱隔离强度不足）")
                }

                Text {
                    typography: Typography.Caption
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: qsTr("TypeType 为中立打字工具，不含广告与聚合搜索；对订阅来源的内容与脚本不承担审核责任，请仅订阅可信来源。")
                }
            }
        }
    }

    WenlaiSection {
        Layout.fillWidth: true
    }

    AiSection {
        Layout.fillWidth: true
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

    KeyboardDevicesSection {
        Layout.fillWidth: true
    }

    // ===================== 关于与更新（ADR-014） =====================
    SettingSectionHeader {
        text: qsTr("关于与更新")
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("当前版本")
        icon.name: "ic_fluent_info_20_regular"
        description: qsTr("检查并安装新版本（自动检查默认开启，可随时手动检查）")

        RowLayout {
            spacing: 8

            Text {
                typography: Typography.Body
                text: "v" + (appBridge ? appBridge.currentVersion : "0.1.0")
                color: Theme.currentTheme.colors.textColor
                Layout.fillWidth: true
            }

            Button {
                id: updateCheckButton
                text: qsTr("检查更新")
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !updateChecking && !updateDownloading
                onClicked: {
                    updateChecking = true
                    updateChecked = false
                    updateErrorText = ""
                    updateVersion = ""
                    updateAvailable = false
                    if (appBridge) appBridge.checkForUpdate()
                }
            }
        }
    }

    SettingCard {
        Layout.fillWidth: true
        visible: updateChecking || updateAvailable || updateErrorText.length > 0 || updateDownloading || updateChecked
        title: updateAvailable
            ? qsTr("发现新版本")
            : (updateErrorText.length > 0
                ? qsTr("检查更新失败")
                : qsTr("更新"))
        icon.name: updateAvailable
            ? "ic_fluent_cloud_arrow_down_20_regular"
            : "ic_fluent_arrow_sync_20_regular"

        ColumnLayout {
            spacing: 8

            // 检查中
            Text {
                visible: updateChecking
                typography: Typography.Caption
                text: qsTr("正在检查更新…")
                color: Theme.currentTheme.colors.textSecondaryColor
            }

            // 无新版（仅在完成过一次手动检查后可见——卡片 visible 靠 updateChecked 撑起）
            Text {
                visible: updateChecked && !updateChecking && !updateAvailable && updateErrorText.length === 0 && !updateDownloading
                typography: Typography.Body
                text: qsTr("已是最新版本")
                color: Theme.currentTheme.colors.systemSuccessColor
            }

            // 有新版
            RowLayout {
                visible: updateAvailable && !updateDownloading
                spacing: 8

                Text {
                    typography: Typography.Body
                    text: qsTr("新版本：") + "v" + updateVersion
                    color: Theme.currentTheme.colors.primaryColor
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Button {
                    text: qsTr("下载并安装")
                    highlighted: true
                    onClicked: {
                        updateDownloading = true
                        updateProgress = 0
                        if (appBridge) appBridge.downloadAndInstallUpdate(updateVersion)
                    }
                }

                ToolButton {
                    flat: true
                    icon.name: "ic_fluent_dismiss_20_regular"
                    ToolTip {
                        text: qsTr("忽略此版本")
                        visible: hovered
                    }
                    onClicked: {
                        if (appBridge) appBridge.dismissUpdate()
                        updateAvailable = false
                        updateVersion = ""
                        updateChecked = false
                    }
                }
            }

            // 下载进度（RinUI ProgressBar，主题化；API 与 QQC 兼容）
            ProgressBar {
                visible: updateDownloading
                Layout.fillWidth: true
                from: 0
                to: 100
                value: updateProgress
                indeterminate: updateProgress <= 0
            }

            Text {
                visible: updateDownloading
                typography: Typography.Caption
                text: updateProgress > 0 ? qsTr("下载中 %1%").arg(updateProgress) : qsTr("准备下载…")
                color: Theme.currentTheme.colors.textSecondaryColor
            }

            // 错误
            Text {
                visible: updateErrorText.length > 0
                typography: Typography.Caption
                text: updateErrorText
                color: Theme.currentTheme.colors.systemCriticalColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onUpdateCheckFinished(available, version, error) {
            var wasManual = updateChecking
            updateChecking = false
            if (error && error.length > 0) {
                updateErrorText = error
                updateAvailable = false
                updateVersion = ""
                return
            }
            updateErrorText = ""
            updateAvailable = available
            updateVersion = available ? version : ""
            // 仅手动检查落地「已是最新」反馈；自动检查（无 updateChecking 前置）静默，
            // 避免后台检查失败被吞后误显示「已是最新版本」
            if (wasManual && !available)
                updateChecked = true
        }

        function onUpdateDownloadProgress(percent) {
            updateProgress = percent
        }

        function onUpdateStatusChanged(status) {
            if (status && status.indexOf("error:") === 0) {
                updateDownloading = false
                updateErrorText = status.substring(6)
            } else if (status === "downloading") {
                updateDownloading = true
            } else if (status === "done") {
                updateDownloading = false
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        // 晴发文（onWenlai*）与 AI（onAiConfigChanged）信号由 settings/WenlaiSection、
        // settings/AiSection 各自内部消费；键盘设备信号由 settings/KeyboardDevicesSection 消费。

        function onZitiSchemesLoaded(items) {
            syncZitiSchemeModel(items)
        }

        function onZitiStateChanged() {
            syncingZitiControls = true
            zitiEnabledSwitch.checked = appBridge.zitiEnabled
            syncingZitiControls = false
        }
    }
}
