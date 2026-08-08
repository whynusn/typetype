import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtCharts
import RinUI

FluentPage {
    id: root
    title: qsTr("个人中心")
    horizontalPadding: 20
    wrapperWidth: 900

    property bool active: false

    readonly property int __xs: 4
    readonly property int __sm: 8
    readonly property int __md: 16
    readonly property int __lg: 24

    onActiveChanged: {
        if (active && appBridge) appBridge.loadTypingHistory();
    }

    // FluentPage 自带 Flickable — content 直接放入内建 ColumnLayout
    ColumnLayout {
        spacing: __lg

            // ============== 用户信息（登录态/未登录态合一） ==============
            Frame {
                Layout.fillWidth: true
                radius: 12
                padding: __md

                RowLayout {
                    anchors.fill: parent
                    spacing: __md

                    Image {
                        source: resourceBaseUrl + "images/TypeTypeLogo.png"
                        Layout.preferredWidth: 56
                        Layout.preferredHeight: 56
                        fillMode: Image.PreserveAspectFit
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: __xs
                        Layout.maximumWidth: parent.width * 0.5

                        Text {
                            typography: Typography.Subtitle
                            text: appBridge && appBridge.loggedin
                                  ? (appBridge.userNickname || qsTr("昵称"))
                                  : qsTr("未登录")
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: appBridge && appBridge.loggedin
                                  ? "@" + (appBridge.currentUser || qsTr("用户名"))
                                  : qsTr("登录后可查看个人统计与历史记录")
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        Layout.alignment: Qt.AlignVCenter
                        typography: Typography.BodyStrong
                        color: Theme.currentTheme.colors.primaryColor
                        text: qsTr("%1 场").arg(appBridge ? appBridge.typingHistoryCount : 0)
                        visible: appBridge && appBridge.loggedin && appBridge.typingHistoryCount > 0
                    }

                    Button {
                        text: appBridge && appBridge.loggedin ? qsTr("退出登录") : qsTr("登录")
                        highlighted: appBridge && appBridge.loggedin ? false : true
                        onClicked: {
                            if (appBridge && appBridge.loggedin)
                                appBridge.logout()
                            else
                                loginDialog.open()
                        }
                    }
                }
            }

            // ============== 统计卡片 ==============
            GridLayout {
                Layout.fillWidth: true
                columnSpacing: __md
                rowSpacing: __md
                columns: root.width >= 760 ? 3 : 2

                Repeater {
                    model: [
                        { label: qsTr("今日字数"), value: appBridge ? appBridge.todayTypedChars : 0, unit: qsTr("字"), icon: "ic_fluent_calendar_20_regular" },
                        { label: qsTr("总字数"), value: appBridge ? appBridge.totalTypedChars : 0, unit: qsTr("字"), icon: "ic_fluent_text_number_list_20_regular" },
                        { label: qsTr("平均速度"), value: (appBridge ? appBridge.typingHistoryAverageSpeed : 0).toFixed(0), unit: qsTr("字/分"), icon: "ic_fluent_speedometer_20_regular" },
                        { label: qsTr("最高速度"), value: (appBridge ? appBridge.typingHistoryMaxSpeed : 0).toFixed(0), unit: qsTr("字/分"), icon: "ic_fluent_flash_20_regular" },
                        { label: qsTr("平均键准"), value: (appBridge ? appBridge.typingHistoryAverageKeyAccuracy : 0).toFixed(1), unit: qsTr("%"), icon: "ic_fluent_target_arrow_20_regular" },
                        { label: qsTr("总场次"), value: appBridge ? appBridge.typingHistoryCount : 0, unit: qsTr("场"), icon: "ic_fluent_ranking_20_regular" }
                    ]

                    Frame {
                        Layout.fillWidth: true
                        radius: 8
                        hoverable: false
                        padding: __md

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: __sm

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: __sm

                                IconWidget {
                                    icon: modelData.icon
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    Layout.alignment: Qt.AlignVCenter
                                    color: Theme.currentTheme.colors.primaryColor
                                }
                                Text {
                                    Layout.fillWidth: true
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.label
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: __xs
                                Layout.leftMargin: 22  // 与标签行的 icon+spacing 对齐

                                Text {
                                    typography: Typography.Title
                                    color: Theme.currentTheme.colors.primaryColor
                                    text: String(modelData.value)
                                }
                                Text {
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.unit
                                }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }

            // ============== 每日打字趋势 ==============
            Frame {
                Layout.fillWidth: true
                radius: 8
                padding: __md

                ColumnLayout {
                    anchors.fill: parent
                    spacing: __sm

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            typography: Typography.BodyStrong
                            text: qsTr("打字趋势")
                        }

                        Item { Layout.fillWidth: true }

                        Segmented {
                            id: trendRangeSelector
                            currentIndex: 1  // 默认"按天"

                            SegmentedItem { text: qsTr("按小时") }
                            SegmentedItem { text: qsTr("按天") }
                            SegmentedItem { text: qsTr("按周") }
                            SegmentedItem { text: qsTr("按月") }

                            onCurrentIndexChanged: {
                                var range = ["hour", "day", "week", "month"][currentIndex]
                                if (appBridge) appBridge.setTrendRange(range)
                            }
                        }
                    }

                    Item {
                        id: trendChart
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180

                        property var trendData: appBridge ? appBridge.typingHistoryDailyTrend : []

                        property var displayData: trendData || []

                        property bool hasData: displayData && displayData.length > 0
                        property real maxChars: {
                            var m = 1;
                            for (var i = 0; i < displayData.length; i++)
                                if (displayData[i] && displayData[i].chars > m) m = displayData[i].chars;
                            return m;
                        }
                        property real axisMax: Math.max(10, Math.ceil(maxChars * 1.15))
                        property int labelStride: displayData.length > 30 ? 6 : (displayData.length > 14 ? 3 : 1)
                        property real plotLeft: trendChartView.plotArea ? trendChartView.plotArea.x : 42
                        property real plotWidth: trendChartView.plotArea ? trendChartView.plotArea.width : Math.max(0, trendChartView.width - plotLeft - 8)
                        property real axisLabelWidth: displayData.length > 14 ? 42 : 56
                        property var chartValues: {
                            var values = []
                            for (var i = 0; i < displayData.length; i++) {
                                var item = displayData[i]
                                values.push(item && item.chars ? Number(item.chars) : 0)
                            }
                            return values
                        }
                        property var chartCategories: {
                            var categories = []
                            for (var i = 0; i < displayData.length; i++)
                                categories.push(String(i + 1))
                            return categories
                        }

                        function formatAxisLabel(item, index) {
                            if (!item || !item.date) return String(index + 1)
                            if (labelStride > 1 && index % labelStride !== 0 && index !== displayData.length - 1)
                                return " "
                            var dateText = item.date
                            var period = item && item.period ? item.period : "day"
                            if (period === "hour" && dateText.length >= 13)
                                return dateText.substring(11, 13) + qsTr("时")
                            if (period === "week") {
                                var weekIndex = dateText.indexOf("-W")
                                return weekIndex >= 0 ? qsTr("第%1周").arg(dateText.substring(weekIndex + 2)) : dateText
                            }
                            if (period === "month" && dateText.length >= 7)
                                return dateText.substring(5, 7) + qsTr("月")
                            if (dateText.length >= 10)
                                return dateText.substring(5, 10)
                            return dateText
                        }

                        ChartView {
                            id: trendChartView
                            anchors.fill: parent
                            anchors.bottomMargin: 28
                            visible: trendChart.hasData
                            antialiasing: true
                            backgroundColor: "transparent"
                            dropShadowEnabled: false
                            legend.visible: false
                            animationOptions: ChartView.SeriesAnimations
                            plotAreaColor: "transparent"
                            margins.top: 0
                            margins.bottom: 0
                            margins.left: 0
                            margins.right: 0

                            BarCategoryAxis {
                                id: trendAxisX
                                categories: trendChart.chartCategories
                                labelsColor: "transparent"
                                lineVisible: false
                            }

                            ValueAxis {
                                id: trendAxisY
                                min: 0
                                max: trendChart.axisMax
                                tickCount: 4
                                labelFormat: "%d"
                                labelsColor: Theme.currentTheme.colors.textSecondaryColor
                                gridLineColor: Theme.currentTheme.colors.dividerBorderColor
                                lineVisible: false
                            }

                            BarSeries {
                                axisX: trendAxisX
                                axisY: trendAxisY
                                barWidth: trendChart.displayData.length > 30 ? 0.45 : 0.72
                                labelsVisible: false

                                BarSet {
                                    label: qsTr("字数")
                                    values: trendChart.chartValues
                                    color: Theme.currentTheme.colors.primaryColor
                                    borderColor: Theme.currentTheme.colors.primaryColor
                                }
                            }
                        }

                        Item {
                            anchors.fill: parent
                            visible: trendChart.hasData

                            Repeater {
                                model: trendChart.displayData

                                Text {
                                    width: trendChart.axisLabelWidth
                                    height: 24
                                    x: trendChart.plotLeft
                                        + ((index + 0.5) / Math.max(1, trendChart.displayData.length)) * trendChart.plotWidth
                                        - width / 2
                                    y: parent.height - height
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                    text: trendChart.formatAxisLabel(modelData, index)
                                }
                            }
                        }

                        // 无数据占位
                        Text {
                            anchors.centerIn: parent
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("暂无趋势数据，多打几局后自动生成")
                            visible: !parent.hasData
                        }
                    }
                }
            }

            // ============== 最近成绩 ==============
            Frame {
                Layout.fillWidth: true
                radius: 8
                padding: __md

                ColumnLayout {
                    anchors.fill: parent
                    spacing: __sm

                    Text {
                        typography: Typography.BodyStrong
                        text: qsTr("最近成绩")
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: __xs

                        Text {
                            id: hDate
                            Layout.fillWidth: true
                            Layout.preferredWidth: 130
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("日期")
                        }
                        Text {
                            id: hSeg
                            Layout.fillWidth: true
                            Layout.preferredWidth: 30
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("段")
                        }
                        Text {
                            id: hSpeed
                            Layout.fillWidth: true
                            Layout.preferredWidth: 70
                            horizontalAlignment: Text.AlignRight
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("速度")
                        }
                        Text {
                            id: hAcc
                            Layout.fillWidth: true
                            Layout.preferredWidth: 70
                            horizontalAlignment: Text.AlignRight
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("键准")
                        }
                        Text {
                            id: hChars
                            Layout.fillWidth: true
                            Layout.preferredWidth: 50
                            horizontalAlignment: Text.AlignRight
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("字数")
                        }
                    }

                    ListView {
                        id: historyList
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(count * 36, 240)
                        Layout.minimumHeight: 60
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        visible: appBridge && appBridge.typingHistoryRecords.length > 0
                        model: appBridge ? appBridge.typingHistoryRecords : []

                        delegate: Rectangle {
                            width: historyList.width
                            height: 36
                            color: index % 2 === 0
                                ? "transparent"
                                : Theme.currentTheme.colors.subtleColor

                            property var rowData: modelData

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: __xs
                                anchors.rightMargin: __xs
                                spacing: __xs

                                Text {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 130
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: rowData ? (rowData.date ? rowData.date.substring(0, 16) : "") : ""
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 30
                                    typography: Typography.Caption
                                    text: rowData ? (rowData.segmentNo || "") : ""
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 70
                                    horizontalAlignment: Text.AlignRight
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.primaryColor
                                    text: rowData ? (rowData.speed !== undefined && rowData.speed !== null ? Number(rowData.speed).toFixed(1) : "-") : "-"
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 70
                                    horizontalAlignment: Text.AlignRight
                                    typography: Typography.Caption
                                    color: {
                                        var ka = rowData ? rowData.keyAccuracy : null;
                                        if (ka === undefined || ka === null) return Theme.currentTheme.colors.textColor;
                                        if (ka >= 98) return Theme.currentTheme.colors.systemSuccessColor;
                                        if (ka >= 95) return Theme.currentTheme.colors.systemAttentionColor;
                                        return Theme.currentTheme.colors.textColor;
                                    }
                                    text: rowData ? (rowData.keyAccuracy !== undefined && rowData.keyAccuracy !== null ? Number(rowData.keyAccuracy).toFixed(1) + "%" : "-") : "-"
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 50
                                    horizontalAlignment: Text.AlignRight
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: rowData ? (rowData.charNum !== undefined && rowData.charNum !== null ? rowData.charNum + qsTr("字") : "-") : "-"
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.RightButton
                                propagateComposedEvents: true
                                onClicked: (mouse) => {
                                    if (mouse.button !== Qt.RightButton || !appBridge) return;
                                    var data = modelData;
                                    if (data && data.scoreText) {
                                        appBridge.copyToClipboard(data.scoreText);
                                        if (Window.window && Window.window.appNotificationManager)
                                            Window.window.appNotificationManager.show(Severity.Success, "", qsTr("已复制到剪贴板"), 1600);
                                    }
                                }
                            }
                        }

                        QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                        Layout.preferredHeight: 60
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("暂无历史记录，打完一局后会自动记录")
                        visible: appBridge && appBridge.typingHistoryRecords.length === 0
                    }
                }
            }
        }

    // ============== 登录弹窗 ==============
    Dialog {
        id: loginDialog
        title: qsTr("登录")
        modal: true
        ColumnLayout { Layout.preferredWidth: 320; spacing: __md
            TextField { id: usernameField; placeholderText: qsTr("用户名"); Layout.fillWidth: true }
            TextField { id: passwordField; placeholderText: qsTr("密码"); echoMode: TextInput.Password; Layout.fillWidth: true }
            InfoBar { id: loginErrorBar; visible: false; severity: Severity.Error; Layout.fillWidth: true; isDynamic: false; closable: false }
            RowLayout { Layout.fillWidth: true; spacing: __sm
                Button { text: qsTr("取消"); Layout.fillWidth: true; onClicked: loginDialog.close() }
                Button { id: loginBtn; text: qsTr("登录"); highlighted: true; Layout.fillWidth: true;
                    onClicked: {
                        var u=usernameField.text.trim(), p=passwordField.text;
                        if (!u||!p){loginErrorBar.text=qsTr("请输入用户名和密码");loginErrorBar.visible=true;return}
                        loginErrorBar.visible=false; loginBtn.enabled=false;
                        if(appBridge) appBridge.login(u,p);
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge; enabled: appBridge !== null
        function onLoginResult(success, message){
            loginBtn.enabled=true;
            if(success) loginDialog.close();
            else {loginErrorBar.text=message; loginErrorBar.visible=true}
        }
        function onRegisterResult(success, message){
            registerBtn.enabled=true;
            if(success) registerDialog.close();
            else {registerErrorBar.text=message; registerErrorBar.visible=true}
        }
    }

    Dialog {
        id: registerDialog
        title: qsTr("注册")
        modal: true
        ColumnLayout { Layout.preferredWidth: 320; spacing: __md
            TextField { id: registerUsernameField; placeholderText: qsTr("用户名（3-20位，字母数字下划线）"); Layout.fillWidth: true }
            TextField { id: registerPasswordField; placeholderText: qsTr("密码（6-30位）"); echoMode: TextInput.Password; Layout.fillWidth: true }
            TextField { id: registerConfirmField; placeholderText: qsTr("确认密码"); echoMode: TextInput.Password; Layout.fillWidth: true }
            TextField { id: registerNicknameField; placeholderText: qsTr("昵称（可选）"); Layout.fillWidth: true }
            InfoBar { id: registerErrorBar; visible: false; severity: Severity.Error; Layout.fillWidth: true; isDynamic: false; closable: false }
            RowLayout { Layout.fillWidth: true; spacing: __sm
                Button { text: qsTr("取消"); Layout.fillWidth: true; onClicked: registerDialog.close() }
                Button { id: registerBtn; text: qsTr("注册"); highlighted: true; Layout.fillWidth: true;
                    onClicked: {
                        var u=registerUsernameField.text.trim(), p=registerPasswordField.text,
                            c=registerConfirmField.text, n=registerNicknameField.text.trim();
                        if (!u||!p){registerErrorBar.text=qsTr("请输入用户名和密码");registerErrorBar.visible=true;return}
                        if (p!==c){registerErrorBar.text=qsTr("两次密码不一致");registerErrorBar.visible=true;return}
                        registerErrorBar.visible=false; registerBtn.enabled=false;
                        if(appBridge) appBridge.register(u,p,n);
                    }
                }
            }
        }
    }
}
