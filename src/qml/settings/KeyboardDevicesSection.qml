import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../components"

// 键盘设备设置区块：设备卡片 + 管理对话框（勾选监听设备/恢复自动发现）。
// 设备列表模型与勾选回写（_populatingDeviceList 锁）自洽于本组件。
ColumnLayout {
    spacing: 4

    property bool _populatingDeviceList: false

    ListModel {
        id: deviceListModel
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

    // 延迟加载键盘设备列表，避免 evdev 扫描阻塞首次页面渲染
    Component.onCompleted: Qt.callLater(_refreshDeviceList)

    SettingSectionHeader {
        text: qsTr("键盘设备")
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

            QQC.ScrollView {
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

            EmptyState {
                text: qsTr("未发现输入设备")
                visible: deviceListModel.count === 0
                Layout.fillWidth: true
            }

            Button {
                text: qsTr("关闭")
                Layout.alignment: Qt.AlignRight
                onClicked: keyboardManagerDialog.close()
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onKeyboardDevicesChanged() {
            _refreshDeviceList()
        }
    }
}
