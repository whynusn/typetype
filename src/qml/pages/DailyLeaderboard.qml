import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    id: dailyLeaderboardPage
    property bool active: false  // 由 NavigationView 注入
    title: qsTr("极速杯日榜")

    // 当前文本信息
    property var currentTextInfo: null
    // 当前排行榜数据
    property var leaderboardRecords: []
    // 文本内容是否展开
    property bool textContentExpanded: false

    // 排行榜表格
    // 错误提示（内联显示，不用 InfoBar 避免定位问题）
    property string errorMessage: ""

    // 内联错误横幅
    Frame {
        Layout.fillWidth: true
        visible: errorMessage !== ""
        radius: 6
        hoverable: false
        color: Theme.currentTheme.colors.systemCriticalBackgroundColor
        padding: 10
        Layout.bottomMargin: 6

        RowLayout {
            anchors.fill: parent
            spacing: 8

            IconWidget {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                icon: "ic_fluent_warning_20_filled"
                color: Theme.currentTheme.colors.systemCriticalColor
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: errorMessage
                wrapMode: Text.WordWrap
            }

            ToolButton {
                icon.name: "ic_fluent_dismiss_20_regular"
                size: 16
                flat: true
                onClicked: errorMessage = ""
            }
        }
    }

    // 排行榜表格
    Frame {
        id: leaderboardFrame
        Layout.fillWidth: true
        // 使用固定高度，因为 FluentPage 内部是 Flickable
        Layout.preferredHeight: 420
        radius: 8
        hoverable: false

        Column {
            anchors.fill: parent
            spacing: 0

            // 表头
            Rectangle {
                width: parent.width
                height: 36
                color: Theme.currentTheme.colors.subtleSecondaryColor

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 4
                    anchors.rightMargin: 4
                    spacing: 0

                    // 排名
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("名次")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 用户
                    Rectangle {
                        Layout.preferredWidth: 100
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("用户")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 速度
                    Rectangle {
                        Layout.preferredWidth: 70
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("速度")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 击键
                    Rectangle {
                        Layout.preferredWidth: 55
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("击键")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 码长
                    Rectangle {
                        Layout.preferredWidth: 50
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("码长")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 键准
                    Rectangle {
                        Layout.preferredWidth: 50
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("键准")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 错字
                    Rectangle {
                        Layout.preferredWidth: 45
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("错字")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 时长
                    Rectangle {
                        Layout.preferredWidth: 50
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("时长")
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                    // 日期
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "transparent"
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("日期")
                        }
                    }
                }
            }

            // 分隔线
            Rectangle {
                width: parent.width
                height: 1
                color: Theme.currentTheme.colors.cardBorderColor
            }

            // 排行榜列表
            ListView {
                id: leaderboardListView
                width: parent.width
                height: parent.height - 37  // 减去表头高度
                clip: true
                model: leaderboardRecords
                delegate: leaderboardDelegate

                QQC.ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                Text {
                    anchors.centerIn: parent
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("暂无排行数据\n点击右上角刷新按钮加载数据")
                    visible: leaderboardListView.count === 0 && !(appBridge && appBridge.leaderboardLoading)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    width: parent.width - 40
                }
            }
        }
    }

    // 文本信息卡片（底部）
    Frame {
        id: textInfoCard
        Layout.fillWidth: true
        visible: currentTextInfo !== null
        // 动态高度：折叠时 80，展开时根据内容
        Layout.preferredHeight: visible ? (textContentExpanded ? Math.min(textContentArea.implicitHeight + 16, 350) : 80) : 0
        radius: 8
        hoverable: false

        // 点击展开/折叠
        MouseArea {
            id: textCardMouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (currentTextInfo && currentTextInfo.content) {
                    textContentExpanded = !textContentExpanded
                }
            }
        }

        ColumnLayout {
            id: textContentArea
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.topMargin: 8
            anchors.bottomMargin: 8
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                spacing: 12

                IconWidget {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    Layout.alignment: Qt.AlignVCenter
                    icon: "ic_fluent_document_text_20_filled"
                    color: Theme.currentTheme.colors.primaryColor
                }

                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    typography: Typography.BodyStrong
                    text: currentTextInfo ? currentTextInfo.title : ""
                    elide: Text.ElideRight
                }

                Text {
                    Layout.alignment: Qt.AlignVCenter
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: currentTextInfo ? qsTr("ID: %1 · %2字").arg(currentTextInfo.id).arg(currentTextInfo.content ? currentTextInfo.content.length : 0) : ""
                }

                // 展开/折叠图标
                IconWidget {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    Layout.alignment: Qt.AlignVCenter
                    icon: textContentExpanded ? "ic_fluent_chevron_up_20_regular" : "ic_fluent_chevron_down_20_regular"
                    color: Theme.currentTheme.colors.textSecondaryColor
                    visible: currentTextInfo && currentTextInfo.content
                }

                // 复制按钮
                ToolButton {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    Layout.alignment: Qt.AlignVCenter
                    icon.name: "ic_fluent_copy_20_regular"
                    size: 16
                    flat: true
                    visible: textContentExpanded && currentTextInfo && currentTextInfo.content
                    onClicked: {
                        if (currentTextInfo && currentTextInfo.content && appBridge) {
                            appBridge.copyToClipboard(currentTextInfo.content)
                            copyToast.show()
                        }
                    }

                    ToolTip {
                        text: qsTr("复制全文")
                        parent: parent
                        visible: parent.hovered
                    }
                }
            }

            // 文本内容（展开时显示）
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: textContentExpanded && currentTextInfo && currentTextInfo.content ? Math.min(textContentText.implicitHeight + 16, 250) : 0
                color: Theme.currentTheme.colors.subtleColor
                radius: 4
                visible: textContentExpanded && currentTextInfo && currentTextInfo.content
                clip: true

                Flickable {
                    id: textFlickable
                    anchors.fill: parent
                    anchors.margins: 8
                    contentWidth: width
                    contentHeight: textContentText.implicitHeight
                    clip: true

                    Text {
                        id: textContentText
                        width: parent.width
                        typography: Typography.Body
                        text: currentTextInfo ? currentTextInfo.content : ""
                        wrapMode: Text.Wrap
                    }

                    QQC.ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }
            }

            // 提示文字（折叠时显示）
            Text {
                Layout.fillWidth: true
                Layout.preferredHeight: 20
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("点击展开查看全文")
                visible: !textContentExpanded && currentTextInfo && currentTextInfo.content
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    // 排行榜项委托
    Component {
        id: leaderboardDelegate

        Rectangle {
            width: leaderboardListView.width
            height: 40
            color: index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor

            // 悬停效果
            property bool hovered: mouseArea.containsMouse
            onHoveredChanged: color = hovered ? Theme.currentTheme.colors.subtleSecondaryColor : (index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor)

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                spacing: 0

                // 排名
                Rectangle {
                    Layout.preferredWidth: 40
                    Layout.fillHeight: true
                    color: "transparent"

                    Row {
                        anchors.centerIn: parent
                        spacing: 2

                        // 奖杯图标（前三名）
                        IconWidget {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 14
                            height: 14
                            visible: modelData.rank <= 3
                            icon: "ic_fluent_trophy_20_filled"
                            color: modelData.rank === 1 ? "#FFD700" :
                                   modelData.rank === 2 ? "#C0C0C0" :
                                   "#CD7F32"
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            color: {
                                if (modelData.rank === 1) return "#FFD700"
                                if (modelData.rank === 2) return "#C0C0C0"
                                if (modelData.rank === 3) return "#CD7F32"
                                return Theme.currentTheme.colors.textColor
                            }
                            text: modelData.rank
                        }
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 用户
                Rectangle {
                    Layout.preferredWidth: 100
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        width: parent.width - 8
                        typography: Typography.Caption
                        text: modelData.nickname || modelData.username || qsTr("匿名")
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 速度
                Rectangle {
                    Layout.preferredWidth: 70
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.primaryColor
                        text: modelData.speed ? Number(modelData.speed).toFixed(1) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 击键
                Rectangle {
                    Layout.preferredWidth: 55
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        text: modelData.keyStroke ? Number(modelData.keyStroke).toFixed(2) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 码长
                Rectangle {
                    Layout.preferredWidth: 50
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        text: modelData.codeLength ? Number(modelData.codeLength).toFixed(3) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 键准
                Rectangle {
                    Layout.preferredWidth: 50
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: {
                            var ka = modelData.keyAccuracy
                            if (ka >= 98) return Theme.currentTheme.colors.systemSuccessColor
                            if (ka >= 95) return Theme.currentTheme.colors.systemAttentionColor
                            return Theme.currentTheme.colors.textColor
                        }
                        text: modelData.keyAccuracy ? Number(modelData.keyAccuracy).toFixed(1) + "%" : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 错字
                Rectangle {
                    Layout.preferredWidth: 45
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: {
                            var wrong = modelData.wrongCharCount
                            if (wrong === 0) return Theme.currentTheme.colors.systemSuccessColor
                            if (wrong <= 5) return Theme.currentTheme.colors.systemAttentionColor
                            return Theme.currentTheme.colors.systemCriticalColor
                        }
                        text: modelData.wrongCharCount !== undefined ? modelData.wrongCharCount : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 时长
                Rectangle {
                    Layout.preferredWidth: 50
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        // 兼容读取：优先读取新字段 time，否则回退到 duration
                        text: {
                            var secs = modelData.time !== undefined ? modelData.time : modelData.duration
                            return secs ? formatDuration(secs) : "-"
                        }
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 日期
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData.createdAt ? formatDate(modelData.createdAt) : "-"
                    }
                }
            }

            // 底部分隔线
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.currentTheme.colors.cardBorderColor
            }
        }
    }

    // 复制成功提示（简单 Toast）
    Rectangle {
        id: copyToast
        // 使用 Layout 属性而非 anchors，因为 FluentPage 内部使用布局管理
        Layout.alignment: Qt.AlignHCenter | Qt.AlignBottom
        Layout.bottomMargin: 80
        Layout.preferredWidth: copyToastText.implicitWidth + 32
        Layout.preferredHeight: 36
        radius: 8
        color: Theme.currentTheme.colors.systemSuccessBackgroundColor
        border.color: Theme.currentTheme.colors.systemSuccessColor
        visible: false
        opacity: visible ? 1 : 0

        Text {
            id: copyToastText
            anchors.centerIn: parent
            typography: Typography.Body
            color: Theme.currentTheme.colors.systemSuccessColor
            text: qsTr("已复制到剪贴板")
        }

        Timer {
            id: copyToastTimer
            interval: 2000
            onTriggered: copyToast.visible = false
        }

        function show() {
            visible = true
            copyToastTimer.restart()
        }
    }

    // 格式化时长（秒 -> 分:秒）
    function formatDuration(seconds) {
        var secs = Number(seconds)
        if (secs < 60) {
            return secs.toFixed(1) + "s"
        }
        var mins = Math.floor(secs / 60)
        var remainSecs = (secs % 60).toFixed(0)
        return mins + ":" + (remainSecs < 10 ? "0" : "") + remainSecs
    }

    // 格式化日期（LocalDateTime 字符串 -> MM-DD HH:mm）
    function formatDate(dateStr) {
        if (!dateStr) return "-"
        // 解析 ISO 格式: 2026-04-09T12:34:56
        var match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
        if (match) {
            var month = match[2]
            var day = match[3]
            var hour = match[4]
            var min = match[5]
            return month + "-" + day + " " + hour + ":" + min
        }
        return dateStr
    }

    // 刷新按钮（放在标题栏右侧）
    extraHeaderItems: [
        Row {
            spacing: 8

            BusyIndicator {
                width: 20
                height: 20
                running: appBridge ? appBridge.leaderboardLoading : false
                visible: running
            }

            ToolButton {
                icon.name: "ic_fluent_arrow_sync_20_regular"
                size: 20
                flat: true
                enabled: appBridge ? !appBridge.leaderboardLoading : false
                onClicked: {
                    if (appBridge) {
                        // 清空旧数据
                        dailyLeaderboardPage.currentTextInfo = null
                        dailyLeaderboardPage.leaderboardRecords = []
                        dailyLeaderboardPage.textContentExpanded = false
                        // 加载极速杯排行榜
                        appBridge.loadLeaderboard("jisubei")
                    }
                }

                ToolTip {
                    text: qsTr("刷新排行榜")
                    parent: parent
                    visible: parent.hovered
                }
            }
        }
    ]

    // 信号连接
    Connections {
        target: appBridge
        enabled: dailyLeaderboardPage.active

        function onLeaderboardLoaded(data) {
            if (data.text_info) {
                dailyLeaderboardPage.currentTextInfo = data.text_info
            }
            if (data.leaderboard) {
                dailyLeaderboardPage.leaderboardRecords = data.leaderboard
            }
            errorMessage = ""
        }

        function onLeaderboardLoadFailed(message) {
            errorMessage = message
        }
    }
}
