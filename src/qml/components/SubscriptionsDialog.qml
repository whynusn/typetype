import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../helpers/SourceBadges.js" as Badges

/**
 * 「我的订阅」：订阅（repo）级列表，与条目快照无关。
 *
 * 为什么需要（2026-10-18 review）：开源文库按源分组展示**快照**，订阅的
 * 管理入口只挂在组头上——首次拉取失败、空源、待信任、已禁用的订阅没有
 * 快照也就没有组头，用户找不到它。这里直接列出配置中的全部订阅，每行给
 * 出健康状态 + 启用开关 + 「管理」（打开 RepoConfigDialog）。
 *
 * 数据源：appBridge.getRepos()（后台加载的摘要）+ reposChanged 信号；
 * 状态文案由 statusText() 统一给出（单一事实源，ui-probe 断言同一属性）。
 */
Dialog {
    id: root

    signal manageRequested(string repoId, string url)
    signal addRequested()

    property var _repos: []
    property bool _syncing: false  // 摘要回写时抑制 Switch 的 onCheckedChanged

    title: qsTr("我的订阅")
    modal: true
    standardButtons: Dialog.Close
    width: Math.min(520, Math.max(300, (QQC.Overlay.overlay ? QQC.Overlay.overlay.width : 544) - 24))
    height: Math.min(480, Math.max(260, (QQC.Overlay.overlay ? QQC.Overlay.overlay.height : 504) - 24))

    // 订阅健康状态（按严重度取第一个命中）
    function statusText(repo) {
        if (!repo) return ""
        if (repo.enabled !== true) return qsTr("已禁用")
        if (repo.incompatible_reason) return qsTr("不兼容：%1").arg(repo.incompatible_reason)
        if (repo.error) return qsTr("清单拉取失败，请检查网络或地址")
        if ((repo.trust_state || "") === "pending") return qsTr("待确认信任（脚本源暂不启用）")
        var n = repo.authorities ? repo.authorities.length : 0
        if (n === 0) return qsTr("清单里没有可用的源")
        return qsTr("%1 个源").arg(n)
    }

    function statusLevel(repo) {
        if (!repo || repo.enabled !== true) return "muted"
        if (repo.incompatible_reason || repo.error) return "critical"
        if ((repo.trust_state || "") === "pending"
                || !repo.authorities || repo.authorities.length === 0) return "caution"
        return "ok"
    }

    function _setRepos(repos) {
        root._syncing = true
        root._repos = repos || []
        root._syncing = false
    }

    onOpened: {
        if (!appBridge) return
        root._setRepos(appBridge.getRepos() || [])
        appBridge.refreshRepos()
    }

    Connections {
        target: appBridge
        function onReposChanged(repos) { root._setRepos(repos) }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("共 %1 个订阅").arg(root._repos.length)
            }
            Button {
                objectName: "subscriptionAddButton"
                text: qsTr("添加订阅")
                icon.name: "ic_fluent_add_20_regular"
                flat: true
                onClicked: root.addRequested()
            }
        }

        ListView {
            id: repoList
            objectName: "subscriptionList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 120
            clip: true
            spacing: 4
            model: root._repos
            QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: row
                objectName: "subscriptionRow"
                required property var modelData
                readonly property string url: modelData.url || ""
                readonly property string statusText: root.statusText(modelData)
                readonly property string statusLevel: root.statusLevel(modelData)
                width: repoList.width
                height: 56
                radius: Utils.radiusCard
                color: Theme.currentTheme.colors.cardColor
                border.color: Theme.currentTheme.colors.cardBorderColor

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 6
                    spacing: 8

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 2

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                text: row.modelData.name || row.url
                                typography: Typography.BodyStrong
                                color: row.modelData.enabled === true
                                       ? Theme.currentTheme.colors.textColor
                                       : Theme.currentTheme.colors.textSecondaryColor
                                elide: Text.ElideRight
                                wrapMode: Text.NoWrap
                            }
                            Rectangle {
                                visible: (row.modelData.trust_state || "") !== ""
                                Layout.preferredWidth: trustText.implicitWidth + 10
                                Layout.preferredHeight: 18
                                radius: Utils.radiusCard
                                readonly property color badgeColor:
                                    Badges.trustColor(row.modelData.trust_state || "", Theme.currentTheme.colors)
                                color: Qt.rgba(badgeColor.r, badgeColor.g, badgeColor.b, 0.18)
                                Text {
                                    id: trustText
                                    anchors.centerIn: parent
                                    text: Badges.trustLabel(row.modelData.trust_state || "")
                                    typography: Typography.Caption
                                    color: parent.badgeColor
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: row.statusText
                            typography: Typography.Caption
                            color: row.statusLevel === "critical"
                                   ? Theme.currentTheme.colors.systemCriticalColor
                                   : row.statusLevel === "caution"
                                     ? Theme.currentTheme.colors.systemCautionColor
                                     : Theme.currentTheme.colors.textSecondaryColor
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                    }

                    Switch {
                        objectName: "subscriptionEnabledSwitch"
                        checked: row.modelData.enabled === true
                        onCheckedChanged: {
                            if (!root._syncing && appBridge
                                    && checked !== (row.modelData.enabled === true))
                                appBridge.setRepoEnabled(row.url, checked)
                        }
                    }

                    Button {
                        objectName: "subscriptionManageButton"
                        text: qsTr("管理")
                        flat: true
                        onClicked: root.manageRequested(row.modelData.repo_id || "", row.url)
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: repoList.count === 0
                text: qsTr("还没有订阅，点「添加订阅」加入源仓库")
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
            }
        }
    }
}
