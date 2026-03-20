// qml/main.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentWindow {
    id: root
    visible: true
    width: 960
    height: 640
    minimumWidth: 640
    minimumHeight: 480
    title: "TypeType"

    // Expose loggedin state to NavigationView for page injection
    property bool loggedin: appBridge ? appBridge.loggedin : false

    navigationItems: [
        {
            title: qsTr("跟打"),
            page: Qt.resolvedUrl("pages/TypingPage.qml"),
            icon: "ic_fluent_keyboard_20_regular",
            position: Position.Top
        },
        {
            title: qsTr("薄弱字"),
            page: Qt.resolvedUrl("pages/WeakCharsPage.qml"),
            icon: "ic_fluent_text_quote_20_regular",
            position: Position.Top
        },
        {
            title: qsTr("排行榜"),
            icon: "ic_fluent_trophy_20_regular",
            subItems: [
                {
                    title: qsTr("日榜"),
                    page: Qt.resolvedUrl("pages/DailyLeaderboard.qml"),
                    icon: "ic_fluent_calendar_day_20_regular"
                },
                {
                    title: qsTr("周榜"),
                    page: Qt.resolvedUrl("pages/WeeklyLeaderboard.qml"),
                    icon: "ic_fluent_calendar_week_start_20_regular"
                },
                {
                    title: qsTr("总榜"),
                    page: Qt.resolvedUrl("pages/AllTimeLeaderboard.qml"),
                    icon: "ic_fluent_data_bar_vertical_star_20_regular"
                }
            ]
        },
        {
            title: qsTr("个人中心"),
            page: Qt.resolvedUrl("pages/ProfilePage.qml"),
            icon: "ic_fluent_person_20_regular",
            position: Position.Bottom
        },
        {
            title: qsTr("设置"),
            page: Qt.resolvedUrl("pages/SettingsPage.qml"),
            icon: "ic_fluent_settings_20_regular",
            position: Position.Bottom
        }
    ]

    defaultPage: Qt.resolvedUrl("pages/TypingPage.qml")
}
