import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../components"

// 阅读字体管理对话框：列出已装字体、切换当前字体、删除/添加自定义字体。
// 字体模型与选中索引由 SettingsPage 持有（单一事实源），选中经 fontSelected 信号回写。
Dialog {
    id: root
    title: qsTr("管理阅读字体")
    modal: true
    standardButtons: Dialog.Close
    width: 420

    property var fontModel
    property int selectedFontIndex: -1

    signal fontSelected(int index, string filePath)

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12

        Text {
            text: {
                if (root.selectedFontIndex >= 0 && root.selectedFontIndex < root.fontModel.count) {
                    var item = root.fontModel.get(root.selectedFontIndex);
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
            visible: root.fontModel.count > 0
        }

        QQC.ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(root.fontModel.count * 40 + 4, 280)
            clip: true
            visible: root.fontModel.count > 0

            ColumnLayout {
                spacing: 2
                width: parent.width

                Repeater {
                    model: root.fontModel

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

                        Behavior on color {
                            ColorAnimation {
                                duration: Utils.animationDuration(Utils.appearanceSpeed)
                                easing.type: Easing.InOutQuart
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: root.fontSelected(fontDlgDelegate.fontIndex, fontDlgDelegate.fontFilePath)
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
                                radius: Utils.radiusSmall
                                color: Theme.currentTheme.colors.primaryColor
                                visible: fontDlgDelegate.fontIndex === root.selectedFontIndex
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
                                ToolTip {
                                    text: qsTr("删除此字体")
                                    visible: hovered
                                }
                            }
                        }
                    }
                }
            }
        }

        EmptyState {
            text: qsTr("暂无字体")
            visible: root.fontModel.count === 0
            Layout.fillWidth: true
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
