import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

/**
 * 开源文库条目列表面板（联邦聚合条目的统一展示）。
 *
 * - 富卡片：来源中文标签 + 「分段」徽章 + 字数 + 标题 + 2 行预览
 * - 来源筛选（RinUI ComboBox）+ 标题/预览搜索
 * - 状态叠加：加载中 / 错误(重试) / 空（引导管理订阅）/ 无匹配
 * - 选中高亮由父级通过 selectedEntry 驱动（entry_id + authority 相等判定）
 */
Frame {
    id: root

    // ---- 输入 ----
    property var entries: []            // 联邦聚合的原始条目 dict
    property bool loading: false
    property string errorText: ""
    property var selectedEntry: null    // 由父级设置，用于卡片高亮

    // ---- 输出 ----
    signal entryClicked(var entry)      // 点击条目，透传原始条目对象
    signal refreshRequested()           // 顶部刷新 / 错误态重试
    signal manageRequested()            // 「管理订阅」按钮
    signal refreshSourceRequested(string authority)  // 单源刷新请求

    // ---- 内部 ----
    property string selectedSourceLabel: ""
    property bool _filterSyncing: false  // ComboBox 模型重建去重守卫

    Layout.fillHeight: true
    Layout.fillWidth: true
    Layout.minimumWidth: 220
    radius: 6
    hoverable: false
    padding: 8

    // 来源中文名映射（source_label → 展示名；未知回退原值）
    function sourceDisplayName(entry) {
        var label = entry.source_label || ""
        var map = {
            "hitokoto": qsTr("一言"),
            "jisubei": qsTr("极速杯"),
            "zenquotes": qsTr("英文名言"),
            "今日诗词（古诗）": qsTr("今日诗词")
        }
        return map[label] || label || qsTr("开源文库")
    }

    // 列表预览：inline 全文（rule/script/bridge）优先，instance 用 preview 摘要
    function entryPreview(entry) {
        return entry.content || entry.preview || ""
    }

    function _charCount(entry) {
        return entry.char_count || entry.charCount || 0
    }

    // 选中判定：entry_id + authority 同时相等才视为同一条目
    function _isSelected(entry) {
        if (!root.selectedEntry || !entry) return false
        return (root.selectedEntry.entry_id || "") === (entry.entry_id || "")
            && (root.selectedEntry.authority || "") === (entry.authority || "")
    }

    function _matches(entry, text) {
        var haystack = (entry.title || "") + " " +
                       (entry.source_label || "") + " " +
                       root.entryPreview(entry)
        return haystack.toLowerCase().indexOf(text) !== -1
    }

    function rebuild() {
        listModel.clear()
        var t = searchField.text.trim().toLowerCase()
        var filterLabel = root.selectedSourceLabel
        for (var i = 0; i < root.entries.length; i++) {
            var e = root.entries[i]
            if (filterLabel.length > 0 && (e.source_label || "") !== filterLabel) continue
            if (t.length > 0 && !root._matches(e, t)) continue
            listModel.append({ entry: e })
        }
    }

    // 重建来源筛选模型，保留之前选中的 label（不存在则回退「全部来源」）
    function rebuildSourceFilter() {
        var prev = (sourceFilterCombo.currentIndex > 0 && sourceFilterCombo.currentIndex < sourceFilterModel.count)
                   ? sourceFilterModel.get(sourceFilterCombo.currentIndex).label : ""
        root._filterSyncing = true
        sourceFilterModel.clear()
        sourceFilterModel.append({ label: qsTr("全部来源") })
        var seen = {}
        for (var i = 0; i < root.entries.length; i++) {
            var label = root.entries[i].source_label || ""
            if (label.length > 0 && !seen[label]) {
                seen[label] = true
                sourceFilterModel.append({ label: label })
            }
        }
        var idx = 0
        if (prev.length > 0) {
            for (var j = 1; j < sourceFilterModel.count; j++) {
                if (sourceFilterModel.get(j).label === prev) { idx = j; break }
            }
        }
        sourceFilterCombo.currentIndex = idx
        root._filterSyncing = false
        root.selectedSourceLabel = (idx > 0) ? prev : ""
        root.rebuild()
    }

    onEntriesChanged: Qt.callLater(rebuildSourceFilter)
    Component.onCompleted: rebuildSourceFilter()

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        // ---- 头部：标题 + 管理订阅 + 刷新 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            spacing: 8

            IconWidget {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                icon: "ic_fluent_cloud_arrow_down_20_regular"
                color: Theme.currentTheme.colors.primaryColor
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.BodyStrong
                text: qsTr("开源文本")
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                running: root.loading
                visible: running
            }

            Item { Layout.fillWidth: true }

            Button {
                text: qsTr("管理订阅")
                icon.name: "ic_fluent_settings_20_regular"
                flat: true
                onClicked: root.manageRequested()
            }

            ToolButton {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                icon.name: "ic_fluent_arrow_sync_20_regular"
                flat: true
                enabled: !root.loading
                onClicked: root.refreshRequested()
                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
            }
        }

        // ---- 筛选行：来源 + 搜索 ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.alignment: Qt.AlignVCenter
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("来源筛选")
            }

            ListModel { id: sourceFilterModel }

            ComboBox {
                id: sourceFilterCombo
                Layout.preferredWidth: 150
                model: sourceFilterModel
                textRole: "label"
                onCurrentIndexChanged: {
                    // textRole/valueRole 下 onActivated 不触发，统一走 currentIndex；
                    // 模型重建期间（_filterSyncing）不响应，防止重复重建
                    if (root._filterSyncing) return
                    root.selectedSourceLabel = (currentIndex > 0 && currentIndex < sourceFilterModel.count)
                                               ? sourceFilterModel.get(currentIndex).label : ""
                    root.rebuild()
                }
            }

            TextField {
                id: searchField
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                placeholderText: qsTr("搜索标题或预览")
                onTextChanged: root.rebuild()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        // ---- 列表区（状态叠加） ----
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            QQC.ScrollView {
                id: listScroll
                anchors.fill: parent
                clip: true
                visible: !root.loading && root.errorText.length === 0 && listModel.count > 0

                ListView {
                    id: listView
                    width: parent.width
                    clip: true
                    spacing: 8
                    boundsBehavior: Flickable.StopAtBounds
                    model: ListModel { id: listModel }

                    delegate: Rectangle {
                        width: listView.width
                        height: cardCol.height + 16
                        radius: 6
                        color: root._isSelected(model.entry)
                               ? Qt.lighter(Theme.currentTheme.colors.cardColor, 1.05)
                               : Theme.currentTheme.colors.cardColor
                        border.color: root._isSelected(model.entry)
                                      ? Theme.currentTheme.colors.primaryColor
                                      : Theme.currentTheme.colors.cardBorderColor
                        border.width: root._isSelected(model.entry) ? 1.5 : 1

                        Column {
                            id: cardCol
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 12
                            spacing: 6

                            // 第一行：来源中文标签 + 内容模式徽章 + 字数
                            RowLayout {
                                width: parent.width
                                spacing: 6

                                Rectangle {
                                    Layout.preferredWidth: labelText.implicitWidth + 12
                                    Layout.preferredHeight: 18
                                    radius: 9
                                    color: Theme.currentTheme.colors.primaryColor
                                    opacity: 0.16
                                    Text {
                                        id: labelText
                                        anchors.centerIn: parent
                                        text: root.sourceDisplayName(model.entry)
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.primaryColor
                                    }
                                }

                                Rectangle {
                                    visible: model.entry.content_mode === "segmented"
                                    Layout.preferredWidth: segText.implicitWidth + 10
                                    Layout.preferredHeight: 18
                                    radius: 9
                                    color: Theme.currentTheme.colors.systemCautionColor
                                    opacity: 0.16
                                    Text {
                                        id: segText
                                        anchors.centerIn: parent
                                        text: qsTr("分段")
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.systemCautionColor
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    visible: text.length > 0
                                    text: root._charCount(model.entry) > 0
                                          ? (root._charCount(model.entry) + " 字" + (model.entry.last_fetched_relative ? " · " + model.entry.last_fetched_relative : ""))
                                          : (model.entry.last_fetched_relative || "")
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                }

                                // 新鲜度徽章（后端 _decorate 输出 freshness）
                                Rectangle {
                                    visible: model.entry.freshness !== undefined && model.entry.freshness !== ""
                                    Layout.preferredWidth: 8
                                    Layout.preferredHeight: 8
                                    radius: 4
                                    color: model.entry.freshness === "on_demand" ? Theme.currentTheme.colors.systemCriticalColor
                                         : model.entry.freshness === "stale" ? Theme.currentTheme.colors.systemCautionColor
                                         : Theme.currentTheme.colors.primaryColor
                                    // Rectangle 无 hovered 属性，需 HoverHandler 提供
                                    HoverHandler { }
                                    ToolTip.visible: hovered
                                    ToolTip.text: model.entry.freshness === "on_demand" ? qsTr("每次随机，可抽新")
                                                : model.entry.freshness === "stale" ? qsTr("已过期，可刷新")
                                                : qsTr("最新")
                                }

                                ToolButton {
                                    Layout.preferredWidth: 24
                                    Layout.preferredHeight: 24
                                    icon.name: "ic_fluent_arrow_sync_20_regular"
                                    flat: true
                                    visible: model.entry.freshness === "stale" || model.entry.freshness === "on_demand"
                                    enabled: !root.loading
                                    onClicked: root.refreshSourceRequested(model.entry.authority || model.entry._authority || "")
                                    ToolTip { text: qsTr("刷新该源"); visible: parent.hovered }
                                }
                            }

                            // 标题
                            Text {
                                width: parent.width
                                text: model.entry.title || model.entry.entry_id || ""
                                typography: Typography.Body
                                color: Theme.currentTheme.colors.textColor
                                elide: Text.ElideRight
                            }

                            // 正文预览（2 行）
                            Text {
                                width: parent.width
                                text: root.entryPreview(model.entry)
                                typography: Typography.Caption
                                color: Theme.currentTheme.colors.textSecondaryColor
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                visible: text.length > 0
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            hoverEnabled: true
                            onClicked: {
                                listView.currentIndex = index
                                root.entryClicked(model.entry)
                            }
                            // 内部标识（authority）作为 ToolTip 展示，不占卡片主体
                            ToolTip.visible: hovered
                            ToolTip.text: model.entry.authority || ""
                            ToolTip.delay: 800
                        }
                    }
                }
            }

            // 加载中
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10
                visible: root.loading

                BusyIndicator {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    running: root.loading
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("正在聚合开源文本...")
                }
            }

            // 错误
            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 32
                spacing: 10
                visible: !root.loading && root.errorText.length > 0

                Text {
                    Layout.fillWidth: true
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.systemCriticalColor
                    text: root.errorText
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }

                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("重试")
                    onClicked: root.refreshRequested()
                }
            }

            // 空（无任何条目）
            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 32
                spacing: 10
                visible: !root.loading && root.errorText.length === 0
                         && listModel.count === 0 && root.entries.length === 0

                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignHCenter
                    typography: Typography.Body
                    color: Theme.currentTheme.colors.textColor
                    text: qsTr("暂无可用条目")
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignHCenter
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: qsTr("可在「管理订阅」中添加或启用源仓库")
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }

                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("管理订阅")
                    onClicked: root.manageRequested()
                }
            }

            // 无匹配（过滤后为空）
            Text {
                anchors.centerIn: parent
                width: parent.width - 24
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("无匹配条目")
                horizontalAlignment: Text.AlignHCenter
                visible: !root.loading && root.errorText.length === 0
                         && listModel.count === 0 && root.entries.length > 0
            }
        }
    }
}
