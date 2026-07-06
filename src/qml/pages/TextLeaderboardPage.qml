import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../typing"

FluentPage {
    id: textLeaderboardPage
    property bool active: false
    title: qsTr("文本排行")

    property bool _sourcesInitialized: false
    property int selectedTextId: -1
    property string selectedTextTitle: ""
    property var leaderboardRecords: []
    property var currentTextInfo: null
    property var textListItems: []
    property string errorMessage: ""

    readonly property bool wideMode: width >= 760

    ListModel { id: sourceListModel }

    function syncSourceOptions(catalog) {
        sourceListModel.clear()
        if (catalog && catalog.length > 0) {
            for (var i = 0; i < catalog.length; i++) {
                sourceListModel.append({ key: catalog[i].key, label: catalog[i].label || catalog[i].key })
            }
            sourceComboBox.currentIndex = _sourcesInitialized ? sourceComboBox.currentIndex : 0
            _sourcesInitialized = true
            var firstKey = catalog[0].key
            if (firstKey && appBridge) appBridge.loadTextList(firstKey)
        }
    }

    function syncTextList(texts) {
        var arr = []
        if (texts) {
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i]
                arr.push({
                    title: t.title || "",
                    subtitle: qsTr("%1 字").arg(t.charCount !== undefined ? t.charCount : 0),
                    raw: { id: t.id || 0, title: t.title || "", char_count: t.charCount || 0 }
                })
            }
        }
        textListItems = arr
        if (arr.length > 0) {
            var first = arr[0].raw
            selectedTextId = first.id
            selectedTextTitle = first.title
            if (appBridge) appBridge.loadLeaderboardByTextId(first.id)
        } else {
            selectedTextId = -1
            selectedTextTitle = ""
            leaderboardRecords = []
            currentTextInfo = null
        }
        errorMessage = ""
    }

    function refreshCurrentSource() {
        if (!appBridge) return
        var idx = sourceComboBox.currentIndex
        var key = (idx >= 0 && idx < sourceListModel.count) ? sourceListModel.get(idx).key : ""
        if (key) {
            selectedTextId = -1
            selectedTextTitle = ""
            leaderboardRecords = []
            currentTextInfo = null
            textListItems = []
            appBridge.loadTextList(key)
        }
    }

    function myRankText() {
        if (!appBridge || !appBridge.loggedin || leaderboardRecords.length === 0) return ""
        var nick = appBridge.userNickname || appBridge.currentUser || ""
        for (var i = 0; i < leaderboardRecords.length; i++) {
            var r = leaderboardRecords[i]
            if ((r.nickname || r.username || "") === nick) {
                return qsTr("我的排名 #%1  速度 %2").arg(r.rank).arg(Number(r.speed).toFixed(1))
            }
        }
        return ""
    }

    function formatDuration(seconds) {
        var secs = Number(seconds)
        if (secs < 60) return secs.toFixed(1) + "s"
        var mins = Math.floor(secs / 60)
        var remainSecs = (secs % 60).toFixed(0)
        return mins + ":" + (remainSecs < 10 ? "0" : "") + remainSecs
    }

    function formatDate(dateStr) {
        if (!dateStr) return "-"
        var match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
        if (match) return match[2] + "-" + match[3] + " " + match[4] + ":" + match[5]
        return dateStr
    }

    horizontalPadding: 20
    wrapperWidth: 1400

    extraHeaderItems: [
        Row {
            spacing: 8
            BusyIndicator {
                width: 20; height: 20
                running: appBridge ? (appBridge.leaderboardLoading || appBridge.textListLoading) : false
                visible: running
            }
            ToolButton {
                icon.name: "ic_fluent_arrow_sync_20_regular"
                size: 20
                flat: true
                enabled: appBridge ? !(appBridge.leaderboardLoading || appBridge.textListLoading) : false
                onClicked: textLeaderboardPage.refreshCurrentSource()
                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
            }
            ToolButton {
                icon.name: "ic_fluent_database_arrow_down_20_regular"
                size: 20
                flat: true
                onClicked: { if (appBridge) appBridge.refreshCatalog() }
                ToolTip { text: qsTr("刷新目录"); visible: parent.hovered }
            }
        }
    ]

    ColumnLayout {
        width: parent.width
        spacing: 14

        // 来源选择 + 错误提示
        Frame {
            Layout.fillWidth: true
            radius: 6
            hoverable: false
            padding: 10
            visible: errorMessage !== ""
            color: Theme.currentTheme.colors.systemCriticalBackgroundColor

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

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ComboBox {
                id: sourceComboBox
                Layout.preferredWidth: 220
                Layout.preferredHeight: 34
                model: sourceListModel
                textRole: "label"
                valueRole: "key"
                onCurrentIndexChanged: {
                    var key = (currentIndex >= 0 && currentIndex < sourceListModel.count)
                        ? sourceListModel.get(currentIndex).key : ""
                    if (key && appBridge) {
                        selectedTextId = -1
                        selectedTextTitle = ""
                        leaderboardRecords = []
                        currentTextInfo = null
                        textListItems = []
                        appBridge.loadTextList(key)
                    }
                }
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("%1 篇文本").arg(textListItems.length)
            }

            Item { Layout.fillWidth: true }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columnSpacing: 12
            rowSpacing: 12
            columns: textLeaderboardPage.wideMode ? 2 : 1

            TextSourceListPanel {
                id: textListPanel
                Layout.fillHeight: true
                Layout.preferredWidth: textLeaderboardPage.wideMode ? Math.max(260, textLeaderboardPage.width * 0.28) : textLeaderboardPage.width
                Layout.maximumWidth: textLeaderboardPage.wideMode ? textLeaderboardPage.width * 0.4 : textLeaderboardPage.width
                title: qsTr("文本列表 (%1)").arg(textListItems.length)
                icon: "ic_fluent_document_text_20_regular"
                sourceItems: textListItems
                loading: appBridge ? appBridge.textListLoading : false
                emptyText: qsTr("暂无文本")
                onItemClicked: {
                    var item = textListPanel.currentItem.raw
                    selectedTextId = item.id
                    selectedTextTitle = item.title
                    if (appBridge) appBridge.loadLeaderboardByTextId(item.id)
                }
            }

            Frame {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 600
                radius: 6
                hoverable: false
                padding: 10

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        IconWidget {
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            icon: "ic_fluent_trophy_20_filled"
                            color: Theme.currentTheme.colors.primaryColor
                        }
                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: {
                                if (selectedTextId < 0) return qsTr("选择文本查看排行榜")
                                var total = currentTextInfo && currentTextInfo.total_participants !== undefined
                                    ? currentTextInfo.total_participants
                                    : leaderboardRecords.length
                                return selectedTextTitle + qsTr(" 的排行榜 (%1人)").arg(total)
                            }
                        }
                        BusyIndicator {
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            running: appBridge ? appBridge.leaderboardLoading : false
                            visible: running
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: myRankText()
                        visible: myRankText().length > 0
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedTextId >= 0

                        Column {
                            anchors.fill: parent
                            spacing: 0

                            Rectangle {
                                width: tableFlickable.contentWidth
                                height: 32
                                color: Theme.currentTheme.colors.subtleSecondaryColor
                                clip: true

                                RowLayout {
                                    id: headerRow
                                    x: -tableFlickable.contentX
                                    width: implicitWidth
                                    height: parent.height
                                    spacing: 0

                                    HeaderCell { text: qsTr("名次"); cellWidth: 60 }
                                    HeaderCell { text: qsTr("用户"); cellWidth: 140 }
                                    HeaderCell { text: qsTr("速度"); cellWidth: 80 }
                                    HeaderCell { text: qsTr("击键"); cellWidth: 70 }
                                    HeaderCell { text: qsTr("码长"); cellWidth: 70 }
                                    HeaderCell { text: qsTr("键准"); cellWidth: 70 }
                                    HeaderCell { text: qsTr("错字"); cellWidth: 60 }
                                    HeaderCell { text: qsTr("时长"); cellWidth: 70 }
                                    HeaderCell { text: qsTr("日期"); cellWidth: 120 }
                                }
                            }

                            Rectangle {
                                width: parent.width
                                height: 1
                                color: Theme.currentTheme.colors.cardBorderColor
                            }

                            Flickable {
                                id: tableFlickable
                                width: parent.width
                                height: parent.height - 33
                                contentWidth: headerRow.implicitWidth
                                contentHeight: height
                                flickableDirection: Flickable.HorizontalFlick
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds

                                QQC.ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

                                Column {
                                    width: tableFlickable.contentWidth
                                    height: parent.height
                                    spacing: 0

                                    ListView {
                                        id: leaderboardListView
                                        width: parent.width
                                        height: parent.height
                                        clip: true
                                        model: leaderboardRecords
                                        interactive: false

                                        QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                        delegate: Rectangle {
                                            width: leaderboardListView.width
                                            height: 36
                                            color: index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor

                                            property bool hovered: lbMouseArea.containsMouse
                                            onHoveredChanged: {
                                                color = hovered ? Theme.currentTheme.colors.subtleSecondaryColor
                                                                : (index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor)
                                            }

                                            MouseArea {
                                                id: lbMouseArea
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                acceptedButtons: Qt.NoButton
                                            }

                                            RowLayout {
                                                anchors.fill: parent
                                                spacing: 0

                                                DataCell {
                    cellWidth: 60
                                                    Row {
                                                        anchors.centerIn: parent
                                                        spacing: 2
                                                        IconWidget {
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            width: 12; height: 12
                                                            visible: modelData.rank <= 3
                                                            icon: "ic_fluent_trophy_20_filled"
                                                            color: modelData.rank === 1 ? "#FFD700" :
                                                                   modelData.rank === 2 ? "#C0C0C0" : "#CD7F32"
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
                                                DataCell {
                    cellWidth: 140
                                                    Text {
                                                        anchors.centerIn: parent
                                                        width: parent.width - 8
                                                        typography: Typography.Caption
                                                        text: modelData.nickname || modelData.username || qsTr("匿名")
                                                        elide: Text.ElideRight
                                                        horizontalAlignment: Text.AlignHCenter
                                                    }
                                                }
                                                DataCell {
                    cellWidth: 80
                                                    Text {
                                                        anchors.centerIn: parent
                                                        typography: Typography.Caption
                                                        color: Theme.currentTheme.colors.primaryColor
                                                        font.weight: Font.DemiBold
                                                        text: modelData.speed ? Number(modelData.speed).toFixed(1) : "-"
                                                    }
                                                }
                                                DataCell {
                    cellWidth: 70
                                                    Text {
                                                        anchors.centerIn: parent
                                                        typography: Typography.Caption
                                                        text: modelData.keyStroke ? Number(modelData.keyStroke).toFixed(2) : "-"
                                                    }
                                                }
                                                DataCell {
                    cellWidth: 70
                                                    Text {
                                                        anchors.centerIn: parent
                                                        typography: Typography.Caption
                                                        text: modelData.codeLength ? Number(modelData.codeLength).toFixed(3) : "-"
                                                    }
                                                }
                                                DataCell {
                    cellWidth: 70
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
                                                DataCell {
                    cellWidth: 60
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
                                                DataCell {
                    cellWidth: 70
                                                    Text {
                                                        anchors.centerIn: parent
                                                        typography: Typography.Caption
                                                        color: Theme.currentTheme.colors.textSecondaryColor
                                                        text: {
                                                            var secs = modelData.time !== undefined ? modelData.time : modelData.duration
                                                            return secs ? formatDuration(secs) : "-"
                                                        }
                                                    }
                                                }
                                                DataCell {
                    cellWidth: 120
                                                    Text {
                                                        anchors.centerIn: parent
                                                        typography: Typography.Caption
                                                        color: Theme.currentTheme.colors.textSecondaryColor
                                                        text: modelData.createdAt ? formatDate(modelData.createdAt) : "-"
                                                    }
                                                }
                                            }
                                        }

                                        Text {
                                            anchors.centerIn: parent
                                            width: parent.width - 40
                                            typography: Typography.Body
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            text: qsTr("暂无排行数据")
                                            horizontalAlignment: Text.AlignHCenter
                                            visible: leaderboardListView.count === 0 && !(appBridge && appBridge.leaderboardLoading)
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedTextId < 0
                        typography: Typography.Body
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("请在左侧选择一个文本查看排行榜")
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: textLeaderboardPage.active

        function onCatalogLoaded(catalog) {
            syncSourceOptions(catalog)
        }

        function onCatalogLoadFailed(message) {
            errorMessage = message
        }

        function onTextListLoaded(texts) {
            syncTextList(texts)
        }

        function onTextListLoadFailed(message) {
            textListItems = []
            selectedTextId = -1
            selectedTextTitle = ""
            errorMessage = message
        }

        function onLeaderboardLoaded(data) {
            if (data.text_info) currentTextInfo = data.text_info
            if (data.leaderboard) leaderboardRecords = data.leaderboard
            errorMessage = ""
        }

        function onLeaderboardLoadFailed(message) {
            leaderboardRecords = []
            errorMessage = message
        }
    }

    onActiveChanged: {
        if (active && appBridge) appBridge.loadCatalog()
    }
}
