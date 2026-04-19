import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

Frame {
    id: root
    radius: 4
    hoverable: false
    color: Theme.currentTheme.colors.cardColor

    property var currentTextInfo: null
    property var leaderboardRecords: []
    property int textId: 0

    signal closeRequested

    // Header — 固定在顶部，不受下方 ColumnLayout 影响
    Rectangle {
        id: headerBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 36
        color: Theme.currentTheme.colors.subtleColor

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 6
            spacing: 6

            IconWidget {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                Layout.alignment: Qt.AlignVCenter
                icon: "ic_fluent_trophy_20_filled"
                color: Theme.currentTheme.colors.primaryColor
            }

            Text {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                typography: Typography.BodyStrong
                font.pixelSize: 13
                text: currentTextInfo ? currentTextInfo.title : qsTr("排行榜")
                elide: Text.ElideRight
            }

            Button {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                flat: true
                enabled: appBridge ? !appBridge.leaderboardLoading : true
                onClicked: {
                    if (appBridge && root.textId > 0) {
                        appBridge.loadLeaderboardByTextId(root.textId);
                    }
                }
                contentItem: IconWidget {
                    icon: "ic_fluent_arrow_sync_20_regular"
                    size: 12
                    color: Theme.currentTheme.colors.textSecondaryColor
                }
            }

            Button {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                text: "✕"
                flat: true
                font.pixelSize: 11
                onClicked: root.closeRequested()
            }
        }
    }

    // Separator under header
    Rectangle {
        id: headerSeparator
        anchors.top: headerBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.currentTheme.colors.cardBorderColor
    }

    ColumnLayout {
        anchors.top: headerSeparator.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        spacing: 0

        // My rank card (compact, visible when logged in and has data)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            visible: appBridge && appBridge.loggedin && leaderboardRecords.length > 0
            color: Theme.currentTheme.colors.subtleSecondaryColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 6

                Text {
                    typography: Typography.Caption
                    font.pixelSize: 12
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("我的排名")
                }

                Text {
                    Layout.fillWidth: true
                    typography: Typography.BodyStrong
                    font.pixelSize: 13
                    color: Theme.currentTheme.colors.primaryColor
                    text: {
                        if (!appBridge || !appBridge.loggedin) return "--";
                        var nick = appBridge.userNickname || appBridge.currentUser || "";
                        for (var i = 0; i < leaderboardRecords.length; i++) {
                            var r = leaderboardRecords[i];
                            if ((r.nickname || r.username || "") === nick) {
                                return "#" + r.rank + "  " + Number(r.speed).toFixed(1);
                            }
                        }
                        return "--";
                    }
                }
            }
        }

        // My rank separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            visible: appBridge && appBridge.loggedin && leaderboardRecords.length > 0
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // Table header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: Theme.currentTheme.colors.subtleColor
            visible: leaderboardRecords.length > 0

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 2

                Text {
                    Layout.preferredWidth: 28
                    typography: Typography.Caption
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    text: qsTr("名次")
                }

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Caption
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    text: qsTr("用户")
                }

                Text {
                    Layout.preferredWidth: 50
                    typography: Typography.Caption
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignRight
                    text: qsTr("速度")
                }
            }
        }

        // Table header separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            visible: leaderboardRecords.length > 0
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // Loading indicator
        BusyIndicator {
            Layout.alignment: Qt.AlignCenter
            Layout.topMargin: 30
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            visible: appBridge && appBridge.leaderboardLoading
        }

        // "本地文本" message
        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 40
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            typography: Typography.Body
            font.pixelSize: 12
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("本地文本不参与排行")
            visible: root.textId === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        // "暂无数据" message
        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 40
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            typography: Typography.Body
            font.pixelSize: 12
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("暂无排行数据")
            visible: root.textId > 0 && leaderboardRecords.length === 0 && !(appBridge && appBridge.leaderboardLoading)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        // Leaderboard list
        ListView {
            id: lbListView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: leaderboardRecords
            visible: leaderboardRecords.length > 0

            delegate: Rectangle {
                width: lbListView.width
                height: 30
                color: index % 2 === 0 ? "transparent" : Theme.currentTheme.colors.subtleColor

                property bool hovered: lbMouseArea.containsMouse
                onHoveredChanged: {
                    color = hovered ? Theme.currentTheme.colors.subtleSecondaryColor :
                        (index % 2 === 0 ? "transparent" : Theme.currentTheme.colors.subtleColor);
                }

                MouseArea {
                    id: lbMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.NoButton
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    spacing: 2

                    // Rank with trophy
                    Row {
                        Layout.preferredWidth: 28
                        spacing: 1

                        IconWidget {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 10
                            height: 10
                            visible: modelData.rank <= 3
                            icon: "ic_fluent_trophy_20_filled"
                            color: modelData.rank === 1 ? "#FFD700" :
                                   modelData.rank === 2 ? "#C0C0C0" :
                                   "#CD7F32"
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            typography: Typography.Caption
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            color: {
                                if (modelData.rank === 1) return "#FFD700";
                                if (modelData.rank === 2) return "#C0C0C0";
                                if (modelData.rank === 3) return "#CD7F32";
                                return Theme.currentTheme.colors.textColor;
                            }
                            text: modelData.rank
                        }
                    }

                    // Name
                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        font.pixelSize: 11
                        text: modelData.nickname || modelData.username || qsTr("匿名")
                        elide: Text.ElideRight
                    }

                    // Speed
                    Text {
                        Layout.preferredWidth: 50
                        typography: Typography.Caption
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        color: Theme.currentTheme.colors.primaryColor
                        horizontalAlignment: Text.AlignRight
                        text: modelData.speed ? Number(modelData.speed).toFixed(1) : "-"
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }

    // 当面板打开且 textId 存在时，自动加载数据
    onVisibleChanged: {
        if (visible && root.textId > 0 && appBridge) {
            appBridge.loadLeaderboardByTextId(root.textId);
        }
    }

    // 当 textId 变化时，清除旧数据或加载新数据
    onTextIdChanged: {
        // 无论 textId 是变有效还是切换到另一个有效值，都先清空避免展示旧数据
        if (root.textId > 0 || root.leaderboardRecords.length > 0) {
            root.leaderboardRecords = [];
            root.currentTextInfo = null;
        }
        if (root.textId > 0 && visible && appBridge) {
            // 本地文本异步回查到 textId 后，面板已可见时自动加载排行榜
            appBridge.loadLeaderboardByTextId(root.textId);
        }
    }

    // Listen for leaderboard updates
    Connections {
        target: appBridge

        function onLeaderboardLoaded(data) {
            root.leaderboardRecords = data.leaderboard || [];
            root.currentTextInfo = data.text_info;
        }

        function onLeaderboardLoadFailed(message) {
            root.leaderboardRecords = [];
        }
    }
}
