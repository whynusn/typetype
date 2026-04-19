import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

Item {
    id: weakCharsPage

    property string sortBy: "error_rate"
    property var sortWeights: ({ "error_rate": 0.6, "total_count": 0.2, "error_count": 0.2 })

    function reloadWeakChars() {
        if (appBridge) {
            var w = sortBy === "weighted" ? sortWeights : {};
            appBridge.loadWeakChars(10, sortBy, w);
        }
    }

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

            RowLayout {
                width: parent.width
                spacing: 8
                Text {
                    text: qsTr("排序方式")
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textSecondaryColor
                }
                ComboBox {
                    id: sortModeCombo
                    Layout.preferredWidth: 140
                    model: ListModel {
                        id: sortModeModel
                        ListElement { text: "按错误率"; value: "error_rate" }
                        ListElement { text: "按错误次数"; value: "error_count" }
                        ListElement { text: "加权评分"; value: "weighted" }
                    }
                    textRole: "text"
                    valueRole: "value"
                    currentIndex: 0
                    onCurrentIndexChanged: {
                        if (currentIndex >= 0 && currentIndex < sortModeModel.count) {
                            var newSort = sortModeModel.get(currentIndex).value;
                            if (newSort !== sortBy) {
                                sortBy = newSort;
                                weightPanel.visible = (sortBy === "weighted");
                                reloadWeakChars();
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }

            RowLayout {
                id: weightPanel
                visible: false
                width: parent.width
                spacing: 12
                // 错误率 weight
                RowLayout {
                    spacing: 4
                    Text { text: "错误率"; color: Theme.currentTheme.colors.textColor; font.pixelSize: 12 }
                    ComboBox {
                        id: errorRateWeight
                        Layout.preferredWidth: 56
                        model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
                        currentIndex: 6
                        onCurrentIndexChanged: { sortWeights.error_rate = parseFloat(model[currentIndex]); reloadWeakChars(); }
                    }
                }
                // 出现频率 weight
                RowLayout {
                    spacing: 4
                    Text { text: "出现频率"; color: Theme.currentTheme.colors.textColor; font.pixelSize: 12 }
                    ComboBox {
                        id: totalCountWeight
                        Layout.preferredWidth: 56
                        model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
                        currentIndex: 2
                        onCurrentIndexChanged: { sortWeights.total_count = parseFloat(model[currentIndex]); reloadWeakChars(); }
                    }
                }
                // 错误次数 weight
                RowLayout {
                    spacing: 4
                    Text { text: "错误次数"; color: Theme.currentTheme.colors.textColor; font.pixelSize: 12 }
                    ComboBox {
                        id: errorCountWeight
                        Layout.preferredWidth: 56
                        model: ["0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"]
                        currentIndex: 2
                        onCurrentIndexChanged: { sortWeights.error_count = parseFloat(model[currentIndex]); reloadWeakChars(); }
                    }
                }
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
        function onTypingEnded() {
            reloadWeakChars();
        }
    }

    StackView.onActivated: {
        if (appBridge) {
            reloadWeakChars();
        }
    }
}
