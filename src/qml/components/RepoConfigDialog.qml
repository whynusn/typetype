import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../helpers/SourceBadges.js" as Badges

/**
 * 订阅源（repo）配置弹窗：管理单个订阅源。
 *
 * 入口：开源文库列表的源组头「管理该源」按钮（manageRepoRequested）。
 * 数据源：appBridge.getRepos()（同步摘要）按 url 匹配当前 repo；
 * 操作（启用/信任/删除）直接走 appBridge 对应 Slot，与订阅管理页同款语义。
 */
Dialog {
    id: root

    property string repoId: ""    // 由入口设置（组头 key）
    property string repoUrl: ""   // 由入口设置（组头 url）
    property var _repo: null      // getRepos() 匹配到的摘要
    property bool _syncingSwitch: false  // 摘要回写时抑制 Switch 的 onCheckedChanged

    title: qsTr("管理订阅源")
    modal: true
    standardButtons: Dialog.Close
    // Popup 非 Item 派生，Window.window 附加属性不可用；Overlay.overlay 支持附加到
    // Popup 且尺寸等于窗口内容区（RinUI Dialog 的 Overlay.modal 同款机制）
    width: Math.min(420, Math.max(280, (QQC.Overlay.overlay ? QQC.Overlay.overlay.width : 444) - 24))
    height: Math.min(420, Math.max(240, (QQC.Overlay.overlay ? QQC.Overlay.overlay.height : 444) - 24))

    // trust 徽章文案与配色统一走 helpers/SourceBadges.js（单一事实源）

    // 摘要回写走此函数：绑定重算会触发 Switch.onCheckedChanged，必须守卫，
    // 否则每次刷新摘要都白调一次 setRepoEnabled（写配置 + refreshRepos）。
    function _setRepo(repo) {
        root._syncingSwitch = true
        root._repo = repo
        root._syncingSwitch = false
    }

    // 打开时重新匹配摘要（启用/信任/删除后摘要会变化）
    onOpened: {
        root._setRepo(null)
        if (appBridge) appBridge.refreshRepos()
    }

    Connections {
        target: appBridge
        function onReposChanged(repos) {
            for (var i = 0; i < repos.length; i++) {
                if ((repos[i].url || "") === root.repoUrl) { root._setRepo(repos[i]); break }
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: 4
        spacing: 10

        // ---- 基本信息 ----
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: root._repo && root._repo.name ? root._repo.name : (root.repoId || qsTr("未知订阅源"))
                typography: Typography.BodyStrong
                color: Theme.currentTheme.colors.textColor
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                HoverHandler { id: repoNameHover }
                ToolTip {
                    text: root._repo && root._repo.name ? root._repo.name : (root.repoId || qsTr("未知订阅源"))
                    visible: repoNameHover.hovered
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: root.repoUrl || root.repoId
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.NoWrap
                elide: Text.ElideMiddle
                HoverHandler { id: repoUrlHover }
                ToolTip {
                    text: root.repoUrl || root.repoId
                    visible: repoUrlHover.hovered
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: text.length > 0
                text: root._repo && root._repo.description ? root._repo.description : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.Wrap
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root._repo && root._repo.maintainer && root._repo.maintainer.name
                      ? qsTr("维护者：%1").arg(root._repo.maintainer.name) : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: text.length > 0
                text: root._repo && root._repo.license
                      ? qsTr("License：%1").arg(root._repo.license) : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root._repo && root._repo.unsupported_sources && root._repo.unsupported_sources.length > 0
                      ? qsTr("不支持源：%1").arg(root._repo.unsupported_sources.join("、")) : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.systemCautionColor
                wrapMode: Text.Wrap
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root._repo && root._repo.incompatible_reason
                      ? qsTr("不兼容：%1").arg(root._repo.incompatible_reason) : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.systemCriticalColor
                wrapMode: Text.Wrap
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // ---- 信任状态 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: qsTr("信任状态")
            }

            Rectangle {
                Layout.preferredWidth: badgeText.implicitWidth + 12
                Layout.preferredHeight: 20
                radius: Utils.radiusCard
                readonly property color badgeColor:
                    Badges.trustColor(root._repo ? root._repo.trust_state || "" : "", Theme.currentTheme.colors)
                color: Qt.rgba(badgeColor.r, badgeColor.g, badgeColor.b, 0.18)
                Text {
                    id: badgeText
                    anchors.centerIn: parent
                    text: Badges.trustLabel(root._repo ? root._repo.trust_state || "" : "")
                    typography: Typography.Caption
                    color: parent.badgeColor
                }
            }

            Item { Layout.fillWidth: true }

            // TOFU pending：信任 / 拒绝
            RowLayout {
                visible: root._repo && (root._repo.trust_state || "") === "pending"
                spacing: 6

                Button {
                    text: qsTr("信任")
                    highlighted: true
                    onClicked: {
                        if (appBridge) appBridge.confirmRepoTrust(root.repoUrl)
                    }
                }
                Button {
                    text: qsTr("拒绝")
                    onClicked: {
                        if (appBridge) appBridge.rejectRepoTrust(root.repoUrl)
                    }
                }
            }
        }

        // ---- 启用/禁用 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: qsTr("启用该订阅源")
            }

            Switch {
                checked: root._repo ? root._repo.enabled === true : false
                onCheckedChanged: {
                    if (!root._syncingSwitch && appBridge && root._repo)
                        appBridge.setRepoEnabled(root.repoUrl, checked)
                }
            }
        }

        Text {
            Layout.fillWidth: true
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            wrapMode: Text.Wrap
            text: qsTr("禁用后该源不再参与聚合（已缓存文本保留，可重新启用）。")
        }

        Item { Layout.fillHeight: true }

        // ---- 危险区：删除订阅 ----
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.Wrap
                text: qsTr("删除订阅将同时清除该源的全部已缓存文本。")
            }

            Button {
                text: qsTr("删除订阅")
                icon.name: "ic_fluent_delete_20_regular"
                onClicked: removeConfirmDialog.open()
            }
        }
    }

    // ---- 删除确认 ----
    Dialog {
        id: removeConfirmDialog
        title: qsTr("确认删除订阅")
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel

        Text {
            text: qsTr("确定删除订阅源「%1」吗？该源的全部已缓存文本将一并清除，此操作不可撤销。")
                .arg(root._repo && root._repo.name ? root._repo.name : root.repoUrl)
            wrapMode: Text.Wrap
            width: 360
        }

        onAccepted: {
            if (appBridge) appBridge.removeRepo(root.repoUrl)
            root.close()
        }
    }
}
