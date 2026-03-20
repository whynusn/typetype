import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

Item {
    id: weakCharsPage

    Flickable {
        anchors.fill: parent
        anchors.margins: 16
        clip: true
        contentWidth: weakCharsPage.width - anchors.margins * 2
        contentHeight: column.height

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        Column {
            id: column
            width: parent.width
            spacing: 12

            Text {
                width: parent.width
                typography: Typography.Title
                text: qsTr("薄弱字")
            }

            Repeater {
                model: ListModel {
                    id: weakCharsModel
                }

                Frame {
                    width: column.width
                    radius: 8
                    hoverable: false
                    height: 72

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 16

                        Text {
                            Layout.preferredWidth: 48
                            Layout.preferredHeight: 48
                            Layout.alignment: Qt.AlignVCenter
                            horizontalAlignment: Qt.AlignHCenter
                            verticalAlignment: Qt.AlignVCenter
                            font.pixelSize: 32
                            font.weight: Font.DemiBold
                            font.family: Utils.fontFamily
                            color: errorRate > 20 ? Theme.currentTheme.colors.systemCriticalColor : (errorRate > 10 ? Theme.currentTheme.colors.systemCautionColor : Theme.currentTheme.colors.systemSuccessColor)
                            text: ch
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                InfoBadge {
                                    count: errorCharCount
                                    severity: errorRate > 20 ? Severity.Error : (errorRate > 10 ? Severity.Warning : Severity.Success)
                                    Layout.alignment: Qt.AlignVCenter
                                }

                                Text {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: qsTr("已打 %1 次").arg(charCount)
                                }

                                Text {
                                    Layout.alignment: Qt.AlignVCenter
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: "⌀ " + avgMs + "ms"
                                }
                            }

                            ProgressBar {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                from: 0
                                to: 100
                                value: errorRate
                                primaryColor: errorRate > 20 ? Theme.currentTheme.colors.systemCriticalColor : (errorRate > 10 ? Theme.currentTheme.colors.systemCautionColor : Theme.currentTheme.colors.systemSuccessColor)
                            }

                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: qsTr("错误率: %1%").arg(errorRate)
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                Text {
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: lastSeen
                                    visible: lastSeen.length > 0
                                }
                            }
                        }
                    }
                }
            }

            Text {
                width: parent.width
                anchors.horizontalCenter: parent.horizontalCenter
                topPadding: 40
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("暂无薄弱字记录，开始打字练习吧！")
                horizontalAlignment: Qt.AlignHCenter
                visible: weakCharsModel.count === 0
            }
        }
    }

    Connections {
        target: appBridge
        function onWeakestCharsLoaded(data) {
            weakCharsModel.clear()
            for (var i = 0; i < data.length; i++) {
                weakCharsModel.append(data[i])
            }
        }
    }

    StackView.onActivating: {
        if (appBridge) {
            appBridge.loadWeakChars()
        }
    }
}
