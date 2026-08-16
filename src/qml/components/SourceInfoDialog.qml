import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

/**
 * 开源文库源详情弹窗（只读信息 + 刷新频率覆盖）。
 *
 * 入口：源组头「源详情」按钮。数据来自快照条目注入的源元数据、
 * appBridge.getFederatedSourceStatuses()（健康状态）与
 * appBridge.getSourceRefreshOverrides()（用户 per-source 覆盖）。
 */
Dialog {
    id: root

    property string authority: ""
    property string sourceLabel: ""
    property string sourceType: ""
    property string repoId: ""
    property string repoUrl: ""
    property var _status: null
    property var _repo: null
    property var _overrides: ({})
    property bool _syncingOverride: false

    title: qsTr("源详情")
    modal: true
    standardButtons: Dialog.Close
    width: 440

    function _tierLabel(type) {
        if (type === "ott-instance") return qsTr("L0 静态实例")
        if (type === "ott-rule") return qsTr("L1 声明式规则")
        if (type === "ott-bridge") return qsTr("L2 桥接")
        if (type === "ott-script") return qsTr("L3 签名脚本")
        return qsTr("未知类型")
    }

    function _policyMode(status) {
        var policy = (status && status.refresh_policy) || {}
        if (policy.mode === "interval") {
            if (policy.interval_seconds <= 3600) return "hourly"
            if (policy.interval_seconds <= 86400) return "daily"
            return "weekly"
        }
        if (policy.mode === "on_demand") return "manual"
        if (policy.mode === "static") return "static"
        return "default"
    }

    function _applyOverride(index) {
        if (root._syncingOverride || !appBridge || !root.authority) return
        if (index === 0) {
            appBridge.clearSourceRefreshOverride(root.authority)
            return
        }
        var mode = "on_demand", seconds = 0
        if (index === 2) { mode = "interval"; seconds = 3600 }
        else if (index === 3) { mode = "interval"; seconds = 86400 }
        else if (index === 4) { mode = "interval"; seconds = 604800 }
        appBridge.setSourceRefreshOverride(root.authority, mode, seconds)
    }

    onOpened: {
        root._status = null
        root._repo = null
        root._overrides = {}
        root._syncingOverride = true
        if (appBridge) {
            var statuses = appBridge.getFederatedSourceStatuses() || {}
            root._status = statuses[root.authority] || null
            root._overrides = appBridge.getSourceRefreshOverrides() || {}
            var repos = appBridge.getRepos() || []
            for (var i = 0; i < repos.length; i++) {
                if ((repos[i].url || "") === root.repoUrl) { root._repo = repos[i]; break }
            }
        }
        var override = root._overrides[root.authority]
        if (override) {
            if (override.mode === "on_demand") refreshModeCombo.currentIndex = 1
            else if (override.interval_seconds <= 3600) refreshModeCombo.currentIndex = 2
            else if (override.interval_seconds <= 86400) refreshModeCombo.currentIndex = 3
            else refreshModeCombo.currentIndex = 4
        } else {
            var mode = root._policyMode(root._status)
            refreshModeCombo.currentIndex =
                mode === "manual" ? 1 :
                mode === "hourly" ? 2 :
                mode === "daily" ? 3 :
                mode === "weekly" ? 4 : 0
        }
        root._syncingOverride = false
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: 4
        spacing: 10

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: root.sourceLabel || root.authority || qsTr("未知源")
                typography: Typography.BodyStrong
                color: Theme.currentTheme.colors.textColor
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Rectangle {
                    Layout.preferredWidth: tierText.implicitWidth + 12
                    Layout.preferredHeight: 20
                    radius: 10
                    color: Theme.currentTheme.colors.controlColor
                    Text {
                        id: tierText
                        anchors.centerIn: parent
                        text: root._tierLabel(root.sourceType)
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textAccentColor
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: root.authority
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    elide: Text.ElideMiddle
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.currentTheme.colors.cardBorderColor }

        // 健康状态
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 4
            columnSpacing: 12

            Text { typography: Typography.Caption; color: Theme.currentTheme.colors.textSecondaryColor; text: qsTr("最近检查") }
            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textColor
                text: root._status && root._status.last_checked_at
                      ? new Date(root._status.last_checked_at * 1000).toLocaleString(Qt.locale())
                      : qsTr("尚未检查")
            }

            Text { typography: Typography.Caption; color: Theme.currentTheme.colors.textSecondaryColor; text: qsTr("最近成功") }
            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textColor
                text: root._status && root._status.last_success_at
                      ? new Date(root._status.last_success_at * 1000).toLocaleString(Qt.locale())
                      : qsTr("无记录")
            }

            Text { typography: Typography.Caption; color: Theme.currentTheme.colors.textSecondaryColor; text: qsTr("最近错误") }
            Text {
                typography: Typography.Caption
                color: root._status && root._status.state === "failed"
                      ? Theme.currentTheme.colors.systemCautionColor
                      : Theme.currentTheme.colors.textColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                text: root._status && root._status.last_error
                      ? (root._status.last_error + (root._status.last_error_at ? " · " + new Date(root._status.last_error_at * 1000).toLocaleString(Qt.locale()) : ""))
                      : qsTr("无")
            }
        }

        // 刷新频率覆盖
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: qsTr("刷新频率")
            }

            ComboBox {
                id: refreshModeCombo
                Layout.preferredWidth: 150
                model: [
                    qsTr("跟随来源声明"),
                    qsTr("仅手动"),
                    qsTr("每小时"),
                    qsTr("每天"),
                    qsTr("每周")
                ]
                onCurrentIndexChanged: {
                    if (root._syncingOverride) return
                    root._applyOverride(currentIndex)
                }
            }
        }

        Text {
            Layout.fillWidth: true
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            wrapMode: Text.Wrap
            text: qsTr("仅手动 = 只在组头点刷新；每小时/每天/每周会在到期时后台自动检查。该设置仅对本源生效。")
        }

        // 所属订阅源
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            visible: root._repo !== null

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("所属订阅源")
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: root._repo && root._repo.name ? root._repo.name : root.repoUrl
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root._repo && root._repo.description ? root._repo.description : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                wrapMode: Text.Wrap
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root._repo && root._repo.license
                      ? qsTr("License：%1").arg(root._repo.license) : ""
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                elide: Text.ElideRight
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

        Item { Layout.fillHeight: true }

        Button {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("立即刷新该源")
            icon.name: "ic_fluent_arrow_sync_20_regular"
            flat: true
            onClicked: {
                if (appBridge) appBridge.refreshFederatedSource(root.authority)
            }
        }
    }
}
