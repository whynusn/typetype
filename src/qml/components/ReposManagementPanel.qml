import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

// ScrollView 使用 QQC 命名空间（QtQuick.Controls 2.15）

/**
 * 源仓库订阅管理面板。
 *
 * OTT Repo 控制面入口：添加订阅 URL、启用/禁用、手动刷新、
 * 信任徽章、按仓库分组展示。
 */
Frame {
    id: root

    // ---- 输入 ----
    property var repos: []
    property bool loading: false

    // ---- 输出 ----
    signal addRepoRequested(string url)
    signal removeRepoRequested(string url)
    signal toggleRepoRequested(string url, bool enabled)
    signal refreshRepoRequested(string url)
    signal refreshAllRequested()
    signal openSourceRequested(string sourceLabel, var authorities)  // 点击源卡片进入条目列表

    // ---- 内部 ----
    property string _newRepoUrl: ""

    function _trustBadge(trustState) {
        if (trustState === "verified") return qsTr("已验证")
        if (trustState === "failed") return qsTr("验证失败")
        return qsTr("未验证")
    }

    function _trustColor(trustState) {
        if (trustState === "verified") return Theme.currentTheme.colors.systemSuccessColor
        if (trustState === "failed") return Theme.currentTheme.colors.systemCriticalColor
        return Theme.currentTheme.colors.textSecondaryColor
    }

    function _sourceTypeSummary(repo) {
        if (!repo) return qsTr("暂无来源")
        if (repo.incompatible_reason) return repo.incompatible_reason
        var auths = repo.authorities || []
        var instances = 0, rules = 0, scripts = 0
        for (var i = 0; i < auths.length; i++) {
            var a = auths[i]
            if (a.indexOf("rule:") === 0) rules = rules + 1
            else if (a === "script") scripts = scripts + 1
            else instances = instances + 1
        }
        var parts = []
        if (instances > 0) parts.push(qsTr("%1 个书库").arg(instances))
        if (rules > 0) parts.push(qsTr("%1 个规则").arg(rules))
        if (scripts > 0) parts.push(qsTr("%1 个脚本").arg(scripts))
        var unsupported = repo.unsupported_sources || []
        if (unsupported.length > 0) parts.push(qsTr("%1 个桥接源（暂不支持）").arg(unsupported.length))
        return parts.join(" · ") || qsTr("暂无来源")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        // ---- 标题 + 全部刷新 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            IconWidget {
                icon: "ic_fluent_cloud_arrow_down_20_regular"
                color: Theme.currentTheme.colors.textColor
            }
            Text {
                text: qsTr("源仓库")
                typography: Typography.BodyStrong
                color: Theme.currentTheme.colors.textColor
                Layout.fillWidth: true
            }
            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                visible: root.loading
                running: root.loading
            }
            ToolButton {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                icon.name: "ic_fluent_arrow_sync_20_regular"
                flat: true
                enabled: !root.loading
                onClicked: root.refreshAllRequested()
                ToolTip { text: qsTr("刷新全部"); visible: parent.hovered }
            }
        }

        // ---- 添加订阅 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            TextField {
                id: urlField
                Layout.fillWidth: true
                placeholderText: qsTr("粘贴源仓库订阅 URL（ott-repo.json）")
                onTextChanged: root._newRepoUrl = text.trim()
            }
            Button {
                text: qsTr("添加")
                enabled: urlField.text.trim().length > 0 && !root.loading
                onClicked: {
                    var u = urlField.text.trim()
                    if (u.length > 0) {
                        root.addRepoRequested(u)
                        urlField.text = ""
                    }
                }
            }
        }

        // ---- 订阅列表 ----
        QQC.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ListView {
                id: repoList
                width: parent.width
                model: root.repos
                spacing: 6
                delegate: Rectangle {
                    id: delegateRoot
                    width: repoList.width
                    radius: 6
                    color: mouseArea.containsMouse ? Theme.currentTheme.colors.controlColor : Theme.currentTheme.colors.cardColor
                    border.color: mouseArea.containsMouse ? Theme.currentTheme.colors.textAccentColor : Theme.currentTheme.colors.cardBorderColor
                    border.width: 1

                    property var repo: modelData
                    /* 高度由 ColumnLayout 的 implicitHeight 驱动，底部留 16px 边距 */
                    height: col.implicitHeight + 16

                    // 点击卡片进入条目列表（在内容下方，Switch/按钮优先响应）
                    MouseArea {
                        id: mouseArea
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: {
                            var r = delegateRoot.repo.raw || delegateRoot.repo
                            root.openSourceRequested(r.name || r.url || "", r.authorities || [])
                        }
                    }

                    ColumnLayout {
                        id: col
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 10
                        spacing: 8

                        // 第一行：名称 + 信任徽章
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: {
                                    var r = delegateRoot.repo.raw || delegateRoot.repo
                                    return r.name || r.url || qsTr("未命名源")
                                }
                                typography: Typography.BodyStrong
                                color: Theme.currentTheme.colors.textColor
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }

                            Rectangle {
                                Layout.preferredWidth: badgeText.implicitWidth + 12
                                Layout.preferredHeight: 20
                                radius: 10
                                color: root._trustColor(delegateRoot.repo.raw ? (delegateRoot.repo.raw.trust_state || delegateRoot.repo.raw.trustState) : "")
                                opacity: 0.18
                                Text {
                                    id: badgeText
                                    anchors.centerIn: parent
                                    text: root._trustBadge(delegateRoot.repo.raw ? (delegateRoot.repo.raw.trust_state || delegateRoot.repo.raw.trustState) : "")
                                    typography: Typography.Caption
                                    color: root._trustColor(delegateRoot.repo.raw ? (delegateRoot.repo.raw.trust_state || delegateRoot.repo.raw.trustState) : "")
                                }
                            }
                        }

                        // 第二行：来源类型统计
                        Text {
                            property var __repo2: delegateRoot.repo.raw || delegateRoot.repo
                            property bool __hasError2: __repo2.error !== undefined && __repo2.error !== null && __repo2.error !== ""
                            text: __hasError2 ? __repo2.error : root._sourceTypeSummary(__repo2)
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            Layout.fillWidth: true
                        }

                        // 第三行：描述（如有）
                        Text {
                            text: (delegateRoot.repo.raw || delegateRoot.repo).description || ""
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            visible: text !== ""
                        }

                        // 第四行：操作行（浏览 + 开关 + 刷新/删除）
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            // 浏览按钮 — 最醒目的入口
                            Button {
                                text: qsTr("浏览文本")
                                highlighted: !root.loading
                                enabled: !root.loading
                                onClicked: {
                                    var r = delegateRoot.repo.raw || delegateRoot.repo
                                    root.openSourceRequested(r.name || r.url || "", r.authorities || [])
                                }
                            }

                            Item { Layout.fillWidth: true }

                            // 启用开关 + 标签
                            RowLayout {
                                spacing: 4
                                Text {
                                    text: qsTr("启用")
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                }
                                Switch {
                                    checked: delegateRoot.repo.raw ? delegateRoot.repo.raw.enabled : false
                                    enabled: !root.loading
                                    onCheckedChanged: root.toggleRepoRequested(delegateRoot.repo.raw ? delegateRoot.repo.raw.url : "", checked)
                                }
                            }

                            ToolButton {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                icon.name: "ic_fluent_arrow_sync_16_regular"
                                flat: true
                                enabled: !root.loading
                                onClicked: root.refreshRepoRequested((delegateRoot.repo.raw || delegateRoot.repo).url)
                                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
                            }
                            ToolButton {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                icon.name: "ic_fluent_delete_16_regular"
                                flat: true
                                enabled: !root.loading
                                onClicked: root.removeRepoRequested((delegateRoot.repo.raw || delegateRoot.repo).url)
                                ToolTip { text: qsTr("移除订阅"); visible: parent.hovered }
                            }
                        }
                    }
                }

                // 空状态
                Text {
                    visible: repoList.count === 0
                    text: qsTr("暂无订阅。粘贴 ott-repo.json URL 添加源仓库。")
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    anchors.centerIn: parent
                    width: parent.width - 32
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
