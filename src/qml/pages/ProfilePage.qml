import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

FluentPage {
    id: root
    title: qsTr("个人中心")
    horizontalPadding: 20
    wrapperWidth: 1100

    onActiveChanged: {
        if (active && appBridge) {
            appBridge.loadTypingHistory();
        }
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth

        ColumnLayout {
            width: root.availableWidth
            spacing: 16

            // ============== 未登录：登录/注册卡片 ==============
            Frame {
                Layout.alignment: Qt.AlignCenter
                Layout.preferredWidth: 360
                Layout.preferredHeight: 180
                radius: 12
                visible: appBridge ? !appBridge.loggedin : true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 16

                    IconWidget {
                        Layout.alignment: Qt.AlignHCenter
                        icon: "ic_fluent_person_20_filled"
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        color: Theme.currentTheme.colors.primaryColor
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        typography: Typography.BodyStrong
                        text: qsTr("登录后可查看个人成绩与统计")
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 12

                        Button {
                            text: qsTr("登录")
                            highlighted: true
                            onClicked: loginDialog.open()
                        }
                        Button {
                            text: qsTr("注册")
                            onClicked: registerDialog.open()
                        }
                    }
                }
            }

            // ============== 已登录：用户信息 ==============
            Frame {
                Layout.fillWidth: true
                radius: 12
                visible: appBridge ? appBridge.loggedin : false

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 16

                    Image {
                        source: resourceBaseUrl + "images/TypeTypeLogo.png"
                        Layout.preferredWidth: 64
                        Layout.preferredHeight: 64
                        fillMode: Image.PreserveAspectFit
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            typography: Typography.Title
                            text: appBridge ? (appBridge.userNickname || qsTr("昵称")) : qsTr("昵称")
                        }
                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: "@" + (appBridge ? (appBridge.currentUser || qsTr("用户名")) : qsTr("用户名"))
                        }
                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("总场次：%1").arg(appBridge ? appBridge.typingHistoryCount : 0)
                        }
                    }

                    Button {
                        text: qsTr("退出登录")
                        onClicked: { if (appBridge) appBridge.logout() }
                    }
                }
            }

            // ============== 统计卡片 ==============
            GridLayout {
                Layout.fillWidth: true
                columnSpacing: 12
                rowSpacing: 12
                columns: root.width >= 760 ? 3 : 2
                visible: appBridge ? appBridge.loggedin : false

                Repeater {
                    model: [
                        { label: qsTr("今日字数"), value: appBridge ? appBridge.todayTypedChars : 0, unit: qsTr("字"), icon: "ic_fluent_calendar_20_regular" },
                        { label: qsTr("总字数"), value: appBridge ? appBridge.totalTypedChars : 0, unit: qsTr("字"), icon: "ic_fluent_text_number_list_20_regular" },
                        { label: qsTr("平均速度"), value: (appBridge ? appBridge.typingHistoryAverageSpeed : 0).toFixed(2), unit: qsTr("字/分"), icon: "ic_fluent_speedometer_20_regular" },
                        { label: qsTr("最高速度"), value: (appBridge ? appBridge.typingHistoryMaxSpeed : 0).toFixed(2), unit: qsTr("字/分"), icon: "ic_fluent_flash_20_regular" },
                        { label: qsTr("平均键准"), value: (appBridge ? appBridge.typingHistoryAverageKeyAccuracy : 0).toFixed(1), unit: qsTr("%"), icon: "ic_fluent_target_arrow_20_regular" },
                        { label: qsTr("总场次"), value: appBridge ? appBridge.typingHistoryCount : 0, unit: qsTr("场"), icon: "ic_fluent_ranking_20_regular" }
                    ]

                    Frame {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 90
                        radius: 8
                        hoverable: false

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 4

                            Text {
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: modelData.label
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                IconWidget {
                                    icon: modelData.icon
                                    Layout.preferredWidth: 18
                                    Layout.preferredHeight: 18
                                    color: Theme.currentTheme.colors.primaryColor
                                }

                                Text {
                                    Layout.fillWidth: true
                                    typography: Typography.Subtitle
                                    text: String(modelData.value)
                                    elide: Text.ElideRight
                            }

                                Text {
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.unit
                                }
                            }
                        }
                    }
                }
            }

            // ============== 每日打字趋势 ==============
            Frame {
                Layout.fillWidth: true
                radius: 8
                visible: appBridge ? appBridge.loggedin : false

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            typography: Typography.BodyStrong
                            text: qsTr("最近 30 天打字量")
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("单位：字")
                        }
                    }

                    // 趋势柱状图
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80

                        property var trendData: appBridge ? appBridge.typingHistoryDailyTrend : []
                        property real maxChars: {
                            var m = 1;
                            for (var i = 0; i < trendData.length; i++) {
                                if (trendData[i] && trendData[i].chars > m) m = trendData[i].chars;
                            }
                            return m;
                        }

                        RowLayout {
                            anchors.fill: parent
                            spacing: 1

                            Repeater {
                                model: parent.parent.trendData

                                Item {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true

                                    Rectangle {
                                        anchors.bottom: parent.bottom
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: parent.width - 1
                                        height: {
                                            var m = parent.parent.maxChars;
                                            return m > 0 ? (modelData.chars / m) * (parent.height - 4) : 0;
                                        }
                                        color: modelData.chars > 0
                                            ? Theme.currentTheme.colors.primaryColor
                                            : Theme.currentTheme.colors.subtleColor
                                        radius: 1
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ============== 最近成绩 ==============
            Frame {
                Layout.fillWidth: true
                radius: 8
                visible: appBridge ? appBridge.loggedin : false

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Text {
                        typography: Typography.BodyStrong
                        text: qsTr("最近成绩")
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    // 表头
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        color: Theme.currentTheme.colors.subtleSecondaryColor

                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.28
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("日期")
                        }
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: parent.width * 0.30
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.12
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("段号")
                        }
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: parent.width * 0.44
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.18
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("速度")
                        }
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: parent.width * 0.62
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.18
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            text: qsTr("键准")
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.14
                            typography: Typography.Caption
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignRight
                            text: qsTr("字数")
                        }
                    }

                    ListView {
                        id: historyList
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(count * 36, 240)
                        Layout.minimumHeight: 54
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        visible: appBridge && appBridge.typingHistoryRecords.length > 0
                        model: appBridge ? appBridge.typingHistoryRecords : []

                        delegate: Rectangle {
                            width: historyList.width
                            height: 36
                            color: index % 2 === 0
                                ? Theme.currentTheme.colors.cardColor
                                : Theme.currentTheme.colors.cardSecondaryColor

                            property var rowData: modelData

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.28
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                text: rowData ? (rowData.date ? rowData.date.substring(0, 16) : "") : ""
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: parent.width * 0.30
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.12
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textColor
                                text: rowData ? (rowData.segmentNo || "") : ""
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: parent.width * 0.44
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.18
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.primaryColor
                                font.weight: Font.DemiBold
                                text: rowData ? (rowData.speed !== undefined && rowData.speed !== null ? Number(rowData.speed).toFixed(1) : "-") : "-"
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: parent.width * 0.62
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.18
                                typography: Typography.Caption
                                color: {
                                    var ka = rowData ? rowData.keyAccuracy : null;
                                    if (ka === undefined || ka === null) return Theme.currentTheme.colors.textColor;
                                    if (ka >= 98) return Theme.currentTheme.colors.systemSuccessColor;
                                    if (ka >= 95) return Theme.currentTheme.colors.systemAttentionColor;
                                    return Theme.currentTheme.colors.textColor;
                                }
                                text: rowData ? (rowData.keyAccuracy !== undefined && rowData.keyAccuracy !== null ? Number(rowData.keyAccuracy).toFixed(1) + "%" : "-") : "-"
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.14
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                horizontalAlignment: Text.AlignRight
                                text: rowData ? (rowData.charNum !== undefined && rowData.charNum !== null ? rowData.charNum + qsTr("字") : "-") : "-"
                                elide: Text.ElideRight
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
                                        if (Window.window && Window.window.appNotificationManager) {
                                            Window.window.appNotificationManager.show(
                                                Severity.Success, "", qsTr("已复制到剪贴板"), 1600);
                                        }
                                    }
                                }
                            }
                        }

                        QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("暂无历史记录，打完一局后会自动记录")
                        visible: appBridge && appBridge.typingHistoryRecords.length === 0
                    }
                }
            }

            Item { Layout.fillHeight: true }

        } // ColumnLayout
    } // ScrollView

    // ============== 登录/注册弹窗 ==============
    Dialog {
        id: loginDialog
        title: qsTr("登录")
        modal: true

        ColumnLayout {
            width: 300
            spacing: 12

            TextField {
                id: usernameField
                placeholderText: qsTr("用户名")
                Layout.fillWidth: true
            }

            TextField {
                id: passwordField
                placeholderText: qsTr("密码")
                echoMode: TextInput.Password
                Layout.fillWidth: true
            }

            Text {
                id: errorText
                visible: false
                color: Theme.currentTheme.colors.systemCriticalColor
                typography: Typography.Caption
                Layout.fillWidth: true
                horizontalAlignment: Qt.AlignCenter
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: qsTr("取消")
                    Layout.fillWidth: true
                    onClicked: loginDialog.close()
                }

                Button {
                    id: loginBtn
                    text: qsTr("登录")
                    highlighted: true
                    Layout.fillWidth: true
                    onClicked: {
                        const username = usernameField.text.trim();
                        const password = passwordField.text;
                        if (!username || !password) {
                            errorText.text = qsTr("请输入用户名和密码");
                            errorText.visible = true;
                            return;
                        }
                        errorText.visible = false;
                        loginBtn.enabled = false;
                        if (appBridge)
                            appBridge.login(username, password);
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null
        function onLoginResult(success, message) {
            loginBtn.enabled = true;
            if (success) {
                loginDialog.close();
            } else {
                errorText.text = message;
                errorText.visible = true;
            }
        }
        function onRegisterResult(success, message) {
            registerBtn.enabled = true;
            if (success) {
                registerDialog.close();
            } else {
                registerErrorText.text = message;
                registerErrorText.visible = true;
            }
        }
    }

    Dialog {
        id: registerDialog
        title: qsTr("注册")
        modal: true

        ColumnLayout {
            width: 300
            spacing: 12

            TextField {
                id: registerUsernameField
                placeholderText: qsTr("用户名（3-20位，字母数字下划线）")
                Layout.fillWidth: true
            }

            TextField {
                id: registerPasswordField
                placeholderText: qsTr("密码（6-30位）")
                echoMode: TextInput.Password
                Layout.fillWidth: true
            }

            TextField {
                id: registerConfirmField
                placeholderText: qsTr("确认密码")
                echoMode: TextInput.Password
                Layout.fillWidth: true
            }

            TextField {
                id: registerNicknameField
                placeholderText: qsTr("昵称（可选）")
                Layout.fillWidth: true
            }

            Text {
                id: registerErrorText
                visible: false
                color: Theme.currentTheme.colors.systemCriticalColor
                typography: Typography.Caption
                Layout.fillWidth: true
                horizontalAlignment: Qt.AlignCenter
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: qsTr("取消")
                    Layout.fillWidth: true
                    onClicked: registerDialog.close()
                }

                Button {
                    id: registerBtn
                    text: qsTr("注册")
                    highlighted: true
                    Layout.fillWidth: true
                    onClicked: {
                        const username = registerUsernameField.text.trim();
                        const password = registerPasswordField.text;
                        const confirm = registerConfirmField.text;
                        const nickname = registerNicknameField.text.trim();
                        if (!username || !password) {
                            registerErrorText.text = qsTr("请输入用户名和密码");
                            registerErrorText.visible = true;
                            return;
                        }
                        if (password !== confirm) {
                            registerErrorText.text = qsTr("两次密码不一致");
                            registerErrorText.visible = true;
                            return;
                        }
                        registerErrorText.visible = false;
                        registerBtn.enabled = false;
                        if (appBridge)
                            appBridge.register(username, password, nickname);
                    }
                }
            }
        }
    }
}
