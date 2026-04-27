// qml/main.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentWindow {
    id: root
    visible: true
    width: 1024
    height: 768
    minimumWidth: 800
    minimumHeight: 520
    title: appBridge ? appBridge.windowTitle : "TypeType"

    // Expose loggedin state to NavigationView for page injection
    property bool loggedin: appBridge ? appBridge.loggedin : false

    onActiveChanged: {
        if (!active && appBridge) {
            appBridge.pauseTypingFromWindowDeactivate()
        } else if (active && appBridge && appBridge.typingPaused) {
            appBridge.toggleTypingPause()
        }
    }

    navigationItems: [
        {
            title: qsTr("跟打"),
            page: Qt.resolvedUrl("pages/TypingPage.qml"),
            icon: "ic_fluent_keyboard_20_regular",
            position: Position.Top
        },
        {
            title: qsTr("本地文库"),
            page: Qt.resolvedUrl("pages/LocalArticlesPage.qml"),
            icon: "ic_fluent_library_20_regular",
            position: Position.None
        },
        {
            title: qsTr("练单器"),
            page: Qt.resolvedUrl("pages/TrainerPage.qml"),
            icon: "ic_fluent_apps_list_detail_20_regular",
            position: Position.None
        },
        {
            title: qsTr("上传文本"),
            page: Qt.resolvedUrl("pages/UploadTextPage.qml"),
            icon: "ic_fluent_document_add_20_regular",
            position: Position.None
        },
        {
            title: qsTr("薄弱字"),
            page: Qt.resolvedUrl("pages/WeakCharsPage.qml"),
            icon: "ic_fluent_text_quote_20_regular",
            position: Position.None
        },
        {
            title: qsTr("文本排行"),
            page: Qt.resolvedUrl("pages/TextLeaderboardPage.qml"),
            icon: "ic_fluent_trophy_20_regular",
            position: Position.None
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
