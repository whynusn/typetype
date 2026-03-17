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

    navigationItems: [
        {
            title: qsTr("跟打"),
            page: Qt.resolvedUrl("pages/TypingPage.qml"),
            icon: "ic_fluent_keyboard_20_regular",
            position: Position.Top
        },
        {
            title: qsTr("排行榜"),
            page: Qt.resolvedUrl("pages/LeaderboardPage.qml"),
            icon: "ic_fluent_trophy_20_regular"
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
