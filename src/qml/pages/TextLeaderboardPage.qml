import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    id: textLeaderboardPage
    title: qsTr("文本排行榜")

    // 减少 FluentPage 默认的大侧边距，给排行榜表格留足空间
    horizontalPadding: 20
    wrapperWidth: 2000

    // 当前选中文本
    property int selectedTextId: -1
    property string selectedTextTitle: ""
    // 当前文本排行榜数据
    property var leaderboardRecords: []
    // 当前文本信息
    property var currentTextInfo: null

    // 文本列表模型
    ListModel {
        id: textListModel
    }

    // 源选项列表模型
    ListModel {
        id: sourceListModel
    }

    // 同步服务端目录到 ListModel
    function syncSourceOptions(catalog) {
        sourceListModel.clear();
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                sourceListModel.append(catalog[i]);
            }
            if (catalog.length > 0) {
                sourceComboBox.currentIndex = 0;
            }
        }
    }

    // ========== 主布局 ==========
    // FluentPage 内部是 Flickable，fillHeight 无法提供有效高度，需要显式计算
    property int _availableHeight: height - (title !== "" ? 80 : 0) - bottomPadding - 18

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

    RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(textLeaderboardPage._availableHeight, 300)
        spacing: 6

        // ========== 左侧文本列表面板 ==========
        Frame {
            Layout.preferredWidth: 180
            Layout.fillHeight: true
            radius: 6
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                // 文本源选择器
                ComboBox {
                    id: sourceComboBox
                    Layout.fillWidth: true
                    model: sourceListModel
                    textRole: "label"
                    valueRole: "key"
                    onCurrentIndexChanged: {
                        // 使用 model.get() 取值，避免 currentValue 绑定时序问题
                        var key = (currentIndex >= 0 && currentIndex < sourceListModel.count)
                            ? sourceListModel.get(currentIndex).key : "";
                        if (key && appBridge) {
                            selectedTextId = -1;
                            selectedTextTitle = "";
                            leaderboardRecords = [];
                            currentTextInfo = null;
                            textListModel.clear();
                            appBridge.loadTextList(key);
                        }
                    }
                }

                // 文本列表标题
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    IconWidget {
                        Layout.preferredWidth: 14
                        Layout.preferredHeight: 14
                        icon: "ic_fluent_document_text_20_regular"
                        color: Theme.currentTheme.colors.primaryColor
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        font.weight: Font.DemiBold
                        text: qsTr("文本列表 (%1)").arg(textListModel.count)
                    }

                    BusyIndicator {
                        Layout.preferredWidth: 14
                        Layout.preferredHeight: 14
                        running: appBridge ? appBridge.textListLoading : false
                        visible: running
                    }
                }

                // 分隔线
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.currentTheme.colors.cardBorderColor
                }

                // 文本列表
                ListView {
                    id: textListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: textListModel
                    delegate: textListDelegate

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("暂无文本")
                        visible: textListModel.count === 0 && !(appBridge && appBridge.textListLoading)
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width - 20
                    }
                }
            }
        }

        // ========== 右侧排行榜面板 ==========
        Frame {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 6
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                // 排行榜标题
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

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
                            if (selectedTextId < 0) return qsTr("选择文本查看排行榜");
                            var info = currentTextInfo;
                            var total = info && info.total_participants !== undefined ? info.total_participants : leaderboardRecords.length;
                            return selectedTextTitle + qsTr(" 的排行榜 (%1人)").arg(total);
                        }
                    }

                    BusyIndicator {
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                        running: appBridge ? appBridge.leaderboardLoading : false
                        visible: running
                    }
                }

                // 分隔线
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.currentTheme.colors.cardBorderColor
                }

                // 排行榜表格（支持水平滚动）
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: selectedTextId >= 0

                    Column {
                        anchors.fill: parent
                        spacing: 0

                        // 表头（同步水平滚动）
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

                                // 排名
                                Rectangle {
                                    Layout.preferredWidth: 50
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
                                    Layout.preferredWidth: 110
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
                                    Layout.preferredWidth: 60
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
                                    Layout.preferredWidth: 60
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

                                // 准确率
                                Rectangle {
                                    Layout.preferredWidth: 65
                                    Layout.fillHeight: true
                                    color: "transparent"
                                    Text {
                                        anchors.centerIn: parent
                                        typography: Typography.Caption
                                        font.weight: Font.DemiBold
                                        text: qsTr("准确率")
                                    }
                                }
                                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                                // 错字
                                Rectangle {
                                    Layout.preferredWidth: 50
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
                                    Layout.preferredWidth: 55
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
                                    Layout.minimumWidth: 90
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

                        // 排行榜列表（水平可滚动）
                        Flickable {
                            id: tableFlickable
                            width: parent.width
                            height: parent.height - 33
                            contentWidth: headerRow.implicitWidth
                            contentHeight: height
                            flickableDirection: Flickable.HorizontalFlick
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds

                            ScrollBar.horizontal: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

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
                                    delegate: leaderboardDelegate
                                    interactive: false

                                    ScrollBar.vertical: ScrollBar {
                                        policy: ScrollBar.AsNeeded
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        typography: Typography.Body
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: qsTr("暂无排行数据")
                                        visible: leaderboardListView.count === 0 && !(appBridge && appBridge.leaderboardLoading)
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                        width: parent.width - 40
                                    }
                                }
                            }
                        }
                    }
                }

                // 未选中文本时的提示
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

    // ========== 文本列表项委托 ==========
    Component {
        id: textListDelegate

        Rectangle {
            width: textListView.width
            height: 48
            radius: 4
            property bool isSelected: model.id === selectedTextId
            color: isSelected ? Qt.rgba(
                Theme.currentTheme.colors.primaryColor.r,
                Theme.currentTheme.colors.primaryColor.g,
                Theme.currentTheme.colors.primaryColor.b,
                0.12
            ) : (textItemMouseArea.containsMouse ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent")
            border.color: isSelected ? Theme.currentTheme.colors.primaryColor : "transparent"
            border.width: isSelected ? 1 : 0

            MouseArea {
                id: textItemMouseArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    selectedTextId = model.id;
                    selectedTextTitle = model.title;
                    if (appBridge) {
                        appBridge.loadLeaderboardByTextId(model.id);
                    }
                }
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 4

                // 选中指示箭头
                Text {
                    Layout.preferredWidth: 10
                    typography: Typography.Caption
                    font.pixelSize: 11
                    color: Theme.currentTheme.colors.primaryColor
                    text: "▸"
                    visible: isSelected
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    // 标题
                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        font.weight: Font.DemiBold
                        font.pixelSize: 11
                        text: model.title || ""
                        elide: Text.ElideRight
                        color: isSelected ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textColor
                    }

                    // 字数
                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        font.pixelSize: 10
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: {
                            var chars = model.char_count !== undefined ? model.char_count : "?";
                            return chars + qsTr("字");
                        }
                        elide: Text.ElideRight
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

    // ========== 排行榜项委托 ==========
    Component {
        id: leaderboardDelegate

        Rectangle {
            width: leaderboardListView.width
            height: 36
            color: index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor

            property bool hovered: lbMouseArea.containsMouse
            onHoveredChanged: color = hovered ? Theme.currentTheme.colors.subtleSecondaryColor : (index % 2 === 0 ? Theme.currentTheme.colors.subtleColor : Theme.currentTheme.colors.cardColor)

            MouseArea {
                id: lbMouseArea
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
            }

            RowLayout {
                anchors.fill: parent
                spacing: 0

                // 排名
                Rectangle {
                    Layout.preferredWidth: 50
                    Layout.fillHeight: true
                    color: "transparent"

                    Row {
                        anchors.centerIn: parent
                        spacing: 2

                        IconWidget {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 12
                            height: 12
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
                    Layout.preferredWidth: 110
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
                        font.weight: Font.DemiBold
                        text: modelData.speed ? Number(modelData.speed).toFixed(1) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 击键
                Rectangle {
                    Layout.preferredWidth: 60
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
                    Layout.preferredWidth: 60
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        text: modelData.codeLength ? Number(modelData.codeLength).toFixed(3) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 准确率
                Rectangle {
                    Layout.preferredWidth: 65
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: {
                            var acc = modelData.accuracyRate
                            if (acc >= 98) return Theme.currentTheme.colors.systemSuccessColor
                            if (acc >= 95) return Theme.currentTheme.colors.systemAttentionColor
                            return Theme.currentTheme.colors.textColor
                        }
                        text: modelData.accuracyRate ? Number(modelData.accuracyRate).toFixed(1) + "%" : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 错字
                Rectangle {
                    Layout.preferredWidth: 50
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
                    Layout.preferredWidth: 55
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData.duration ? formatDuration(modelData.duration) : "-"
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.currentTheme.colors.cardBorderColor }

                // 日期
                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 90
                    Layout.fillHeight: true
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        Component.onCompleted: {
                            if (!modelData.createdAt) {
                                console.log("[DEBUG] LB record keys:", JSON.stringify(Object.keys(modelData)))
                            }
                        }
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

    // ========== 刷新按钮（标题栏右侧） ==========
    extraHeaderItems: [
        Row {
            spacing: 8

            BusyIndicator {
                width: 20
                height: 20
                running: appBridge ? (appBridge.leaderboardLoading || appBridge.textListLoading) : false
                visible: running
            }

            ToolButton {
                icon.name: "ic_fluent_arrow_sync_20_regular"
                size: 20
                flat: true
                enabled: appBridge ? !(appBridge.leaderboardLoading || appBridge.textListLoading) : false
                onClicked: {
                    if (appBridge) {
                        // 刷新当前选中来源的文本列表，不重置 ComboBox
                        var idx = sourceComboBox.currentIndex;
                        var key = (idx >= 0 && idx < sourceListModel.count)
                            ? sourceListModel.get(idx).key : "";
                        if (key) {
                            textListModel.clear();
                            selectedTextId = -1;
                            selectedTextTitle = "";
                            leaderboardRecords = [];
                            currentTextInfo = null;
                            appBridge.loadTextList(key);
                        }
                    }
                }

                ToolTip {
                    text: qsTr("刷新")
                    parent: parent
                    visible: parent.hovered
                }
            }

            ToolButton {
                icon.name: "ic_fluent_database_arrow_down_20_regular"
                size: 20
                flat: true
                onClicked: {
                    if (appBridge) {
                        appBridge.refreshCatalog();
                    }
                }

                ToolTip {
                    text: qsTr("刷新目录")
                    parent: parent
                    visible: parent.hovered
                }
            }
        }
    ]

    // 错误提示（内联显示，不用 InfoBar 避免定位问题）
    property string errorMessage: ""

    // ========== 主布局 ==========

    // ========== 信号连接 ==========
    // catalogLoaded 信号需要 StackView.status 守卫，防止页面切换期间触发 loadTextList 级联调用
    Connections {
        target: appBridge
        enabled: textLeaderboardPage.StackView.status === StackView.Active

        function onCatalogLoaded(catalog) {
            syncSourceOptions(catalog);
            // syncSourceOptions 设 currentIndex=0 会自动触发 loadTextList，无需显式调用
        }

        function onCatalogLoadFailed(message) {
            errorMessage = message;
        }
    }

    // 文本列表和排行榜信号来自异步 Worker，需要守卫防止旧实例处理
    Connections {
        target: appBridge
        enabled: textLeaderboardPage.StackView.status === StackView.Active

        function onTextListLoaded(texts) {
            textListModel.clear();
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i];
                // 服务端 clientTextId 可能为 null，ListModel 不接受 undefined 成员
                textListModel.append({
                    id: t.id || 0,
                    title: t.title || "",
                    char_count: t.charCount || 0,
                    clientTextId: t.clientTextId || 0
                });
            }
            // 自动选中第一个文本
            if (texts.length > 0) {
                selectedTextId = texts[0].id;
                selectedTextTitle = texts[0].title;
                appBridge.loadLeaderboardByTextId(texts[0].id);
            }
            errorMessage = "";
        }

        function onTextListLoadFailed(message) {
            textListModel.clear();
            errorMessage = message;
        }

        function onLeaderboardLoaded(data) {
            if (data.text_info) {
                currentTextInfo = data.text_info;
            }
            if (data.leaderboard) {
                leaderboardRecords = data.leaderboard;
            }
            errorMessage = "";
        }

        function onLeaderboardLoadFailed(message) {
            leaderboardRecords = [];
            errorMessage = message;
        }
    }

    // ========== 页面激活时加载数据 ==========
    StackView.onActivated: {
        if (appBridge) {
            appBridge.refreshCatalog();
        }
    }

}
