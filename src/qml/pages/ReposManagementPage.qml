import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../components"

/**
 * 源仓库订阅管理页。
 *
 * 独立承载 OTT Repo 控制面（原 TextLoadHubPage「源仓库」标签职责）：
 * - 激活/完成时刷新订阅摘要
 * - 面板信号全部转发到 appBridge 对应 Slot
 * - 「浏览文本」改为返回上一页（浏览在载文中心开源文库标签完成）
 */
FluentPage {
    id: root

    title: qsTr("管理源仓库")
    horizontalPadding: 20
    wrapperWidth: 1000

    property bool active: false  // 由 NavigationView 注入
    property var reposItems: []
    property string errorMessage: ""
    property bool loading: appBridge ? appBridge.reposLoading : false

    // ---- 激活/初始化刷新 ----
    onActiveChanged: {
        if (active && appBridge) appBridge.refreshRepos()
    }
    Component.onCompleted: {
        if (appBridge) appBridge.refreshRepos()
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onReposChanged(list) {
            root.reposItems = list
            root.errorMessage = ""
        }
        function onReposLoadFailed(msg) {
            root.errorMessage = msg
        }
    }

    // ---- 内容 ----
    ColumnLayout {
        width: parent.width
        spacing: 8

        ReposManagementPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            repos: root.reposItems
            loading: root.loading

            onAddRepoRequested: function(url) { if (appBridge) appBridge.addRepo(url) }
            onRemoveRepoRequested: function(url) { if (appBridge) appBridge.removeRepo(url) }
            onToggleRepoRequested: function(url, enabled) { if (appBridge) appBridge.setRepoEnabled(url, enabled) }
            onRefreshRepoRequested: function(url) { if (appBridge) appBridge.refreshRepo(url) }
            onRefreshAllRequested: { if (appBridge) appBridge.refreshRepos() }
            onConfirmRepoRequested: function(url) { if (appBridge) appBridge.confirmRepoTrust(url) }
            onRejectRepoRequested: function(url) { if (appBridge) appBridge.rejectRepoTrust(url) }
            onOpenSourceRequested: function(sourceLabel, authorities) {
                // 浏览改在载文中心「开源文库」标签完成，这里直接返回上一页
                if (Window.window && Window.window.navigationView) {
                    Window.window.navigationView.pop()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: 20
            typography: Typography.Caption
            color: Theme.currentTheme.colors.systemCriticalColor
            text: root.errorMessage
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            visible: root.errorMessage.length > 0
        }
    }
}
