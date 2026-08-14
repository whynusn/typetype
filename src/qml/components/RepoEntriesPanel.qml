import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

/**
 * 开源文库条目列表面板（联邦聚合条目的统一展示）。
 *
 * - 按订阅源（repo）动态分组：条目物化时注入 _repo_id（federation
 *   `_decorate_with_repo_meta`），条目属于哪个订阅源就归入哪个源组——
 *   纯动态归属，不硬编码。组头 = 展开/收起 + 源名 + 条目数（x / 上限）+ 
 *   源级刷新（动画只在组头播放一份）+ 管理按钮
 * - 组头可展开/收起（_expanded 状态；折叠时组内条目不渲染）
 * - 组内条目卡片：「分段」徽章 + 字数 + 新鲜度 + 标题 + 2 行预览
 * - 来源筛选（RinUI ComboBox）+ 标题/预览搜索（作用于条目，空组不渲染）
 * - 状态叠加：加载中 / 错误(重试) / 空（引导添加订阅）/ 无匹配
 * - 选中高亮由父级通过 selectedEntry 驱动（entry_id + authority 相等判定）
 */
Frame {
    id: root

    // ---- 输入 ----
    property var entries: []            // 联邦聚合的原始条目 dict
    property bool loading: false
    property string errorText: ""
    property var selectedEntry: null    // 由父级设置，用于卡片高亮
    // 正在刷新的订阅源 repo_id（'' = 无）：驱动「源组头」刷新动画（一份）。
    // 与 loading 分层：列表级刷新（顶部/右侧）盖整列表动画，repo 刷新
    // 只在对应源组头转圈，列表保持可交互。
    property string refreshingRepo: ""

    // ---- 输出 ----
    signal entryClicked(var entry)      // 点击条目，透传原始条目对象
    signal refreshRequested()           // 顶部刷新 / 错误态重试
    signal addRepoRequested()           // 「添加订阅」按钮
    signal refreshRepoRequested(string repoId)  // 订阅源（repo）级刷新请求
    signal manageRepoRequested(string repoId, string url)  // 进入该源管理

    // ---- 内部 ----
    property string selectedSourceLabel: ""
    property bool _filterSyncing: false  // ComboBox 模型重建去重守卫
    // 组展开状态（key = repo_id/authority；缺省展开）
    property var _expanded: ({})

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

    // 组刷新动画判定：该组（repo_id）正在被刷新 → 组头播放一份动画
    function _isRefreshingGroup(group) {
        if (!group || root.refreshingRepo.length === 0) return false
        return root.refreshingRepo === (group.key || "")
    }

    function _matches(entry, text) {
        var haystack = (entry.title || "") + " " +
                       (entry.source_label || "") + " " +
                       root.entryPreview(entry)
        return haystack.toLowerCase().indexOf(text) !== -1
    }

    // 组头展开/收起切换（折叠时组内条目不渲染）
    function toggleGroup(key) {
        root._expanded[key] = !(root._expanded[key] === false)
        root.rebuild()
    }

    // 按订阅源（_repo_id）动态分组重建模型：每组先插「组头」行（源名/计数/
    // 折叠状态/上限），再插组内条目行。筛选/搜索作用于条目，空组不渲染。
    function rebuild() {
        listModel.clear()
        var t = searchField.text.trim().toLowerCase()
        var filterLabel = root.selectedSourceLabel
        var headerRows = {}  // group key -> 组头行 index（组内计数累加用）
        for (var i = 0; i < root.entries.length; i++) {
            var e = root.entries[i]
            if (filterLabel.length > 0 && (e.source_label || "") !== filterLabel) continue
            if (t.length > 0 && !root._matches(e, t)) continue
            // 动态分组键：条目属于哪个订阅源就归入哪个源组（federation 注入）
            var key = e._repo_id || e.authority || e._authority || ""
            if (headerRows[key] === undefined) {
                headerRows[key] = listModel.count
                listModel.append({
                    kind: "header",
                    group: {
                        key: key,
                        name: e._repo_name || root.sourceDisplayName(e),
                        subtitle: key,
                        url: e._repo_url || "",
                        count: 0,
                        maxEntries: e._repo_max_entries || 0,
                        collapsed: root._expanded[key] === false
                    }
                })
            }
            var g = listModel.get(headerRows[key]).group
            g.count++
            listModel.set(headerRows[key], { kind: "header", group: g })
            if (root._expanded[key] === false) continue  // 折叠：不渲染条目行
            listModel.append({ kind: "entry", entry: e })
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

        // ---- 头部：标题 + 添加订阅 + 刷新 ----
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
                text: qsTr("添加订阅")
                icon.name: "ic_fluent_add_20_regular"
                flat: true
                onClicked: root.addRepoRequested()
            }

            ToolButton {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                icon.name: "ic_fluent_arrow_sync_20_regular"
                flat: true
                enabled: !root.loading
                onClicked: root.refreshRequested()
                ToolTip { text: qsTr("刷新全部"); visible: parent.hovered }
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

                    // 双组件 delegate：header/entry 各自只引用自己的 role，
                    // 避免不可见分支的绑定对 undefined role 求值报 TypeError
                    delegate: Loader {
                        id: loader
                        width: listView.width
                        height: item ? item.height : 0
                        property var groupData: model.kind === "header" ? model.group : null
                        property var entryData: model.kind === "entry" ? model.entry : null
                        sourceComponent: model.kind === "header" ? headerComponent : entryComponent
                        /* ⚠️ 两个组件必须声明为 delegate Loader 的直接子项：
                           Loader 实例化「外部声明的 Component」时，加载项的 QML
                           上下文是组件声明处（ListView 作用域），看不到 delegate
                           的 loader id 与 model/index 上下文属性——此前声明在
                           ListView 下，全部 header/entry 绑定抛 ReferenceError
                           "loader is not defined" / "model is not defined"
                           （2026-08-14 全应用实测）。声明为 Loader 子项后加载项
                           继承 delegate 上下文，loader.groupData /
                           loader.entryData / model.* 均可解析。 */

                    // ================= 组头：订阅源 =================
                    Component {
                        id: headerComponent

                        Rectangle {
                            width: listView.width
                            height: 46
                            radius: 6
                            color: Theme.currentTheme.colors.controlColor
                            border.color: Theme.currentTheme.colors.cardBorderColor
                            border.width: 1

                            // 整行点击 = 展开/收起（按钮子项位于其上方优先响应）
                            MouseArea {
                                id: headerMouse
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: root.toggleGroup(loader.groupData.key)
                            }

                            RowLayout {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                spacing: 8

                                IconWidget {
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    icon: loader.groupData.collapsed
                                           ? "ic_fluent_chevron_right_20_regular"
                                           : "ic_fluent_chevron_down_20_regular"
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0

                                    Text {
                                        Layout.fillWidth: true
                                        text: loader.groupData.name
                                        typography: Typography.BodyStrong
                                        color: Theme.currentTheme.colors.textColor
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: loader.groupData.subtitle
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        elide: Text.ElideRight
                                    }
                                }

                                // 文本计数：当前已有 / 订阅源规定的上限（无上限只显示当前数）
                                Text {
                                    text: {
                                        var s = qsTr("%1 条").arg(loader.groupData.count)
                                        if (loader.groupData.maxEntries > 0)
                                            s = qsTr("%1 / %2 条").arg(loader.groupData.count).arg(loader.groupData.maxEntries)
                                        return s
                                    }
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                }

                                // 源级刷新：一个源无论多少文本，动画只在组头播放一份
                                ToolButton {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                    icon.name: "ic_fluent_arrow_sync_20_regular"
                                    flat: true
                                    visible: !root._isRefreshingGroup(loader.groupData)
                                    enabled: !root.loading
                                    onClicked: root.refreshRepoRequested(loader.groupData.key)
                                    ToolTip { text: qsTr("刷新该源"); visible: parent.hovered }
                                }
                                BusyIndicator {
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    running: root._isRefreshingGroup(loader.groupData)
                                    visible: running
                                }

                                // 管理该订阅源（进入配置弹窗）
                                ToolButton {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                    icon.name: "ic_fluent_settings_20_regular"
                                    flat: true
                                    onClicked: root.manageRepoRequested(loader.groupData.key, loader.groupData.url)
                                    ToolTip { text: qsTr("管理该源"); visible: parent.hovered }
                                }
                            }
                        }
                    }

                    // ================= 条目卡片 =================
                    Component {
                        id: entryComponent

                        Rectangle {
                            id: entryRoot
                            width: listView.width
                            height: cardCol.height + 16
                            radius: 6

                            readonly property var entry: loader.entryData
                            readonly property bool isSelected: root._isSelected(loader.entryData)

                            color: cardMouse.containsMouse && !isSelected
                                   ? Theme.currentTheme.colors.controlColor
                                   : (isSelected
                                      ? Qt.lighter(Theme.currentTheme.colors.cardColor, 1.05)
                                      : Theme.currentTheme.colors.cardColor)
                            border.color: cardMouse.containsMouse && !isSelected
                                          ? Theme.currentTheme.colors.textAccentColor
                                          : (isSelected
                                             ? Theme.currentTheme.colors.primaryColor
                                             : Theme.currentTheme.colors.cardBorderColor)
                            border.width: isSelected ? 1.5 : 1

                            // 整卡点击区（内容子项位于其上方、优先接收点击）
                            MouseArea {
                                id: cardMouse
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: {
                                    listView.currentIndex = index
                                    root.entryClicked(loader.entryData)
                                }
                            }

                            Column {
                                id: cardCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 12
                                spacing: 6

                                // 第一行：内容模式徽章 + 字数 + 新鲜度状态（源名已在组头）
                                RowLayout {
                                    width: parent.width
                                    spacing: 6

                                    Rectangle {
                                        visible: loader.entryData.content_mode === "segmented"
                                        Layout.preferredWidth: segText.implicitWidth + 10
                                        Layout.preferredHeight: 18
                                        radius: 9
                                        color: Qt.rgba(Theme.currentTheme.colors.systemCautionColor.r,
                                                       Theme.currentTheme.colors.systemCautionColor.g,
                                                       Theme.currentTheme.colors.systemCautionColor.b, 0.16)
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
                                        text: root._charCount(loader.entryData) > 0
                                              ? (root._charCount(loader.entryData) + " 字" + (loader.entryData.last_fetched_relative ? " · " + loader.entryData.last_fetched_relative : ""))
                                              : (loader.entryData.last_fetched_relative || "")
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                    }

                                    // 新鲜度状态标签（后端 _decorate 输出 freshness：on_demand 随机 / stale 可刷新 / fresh 最新）
                                    Rectangle {
                                        visible: model.entry.freshness !== undefined && model.entry.freshness !== ""
                                        Layout.preferredWidth: freshText.implicitWidth + 12
                                        Layout.preferredHeight: 18
                                        radius: 9
                                        readonly property color freshColor:
                                            model.entry.freshness === "on_demand" ? Theme.currentTheme.colors.primaryColor
                                            : model.entry.freshness === "stale" ? Theme.currentTheme.colors.systemCautionColor
                                            : Theme.currentTheme.colors.systemSuccessColor
                                        // 只给背景降透明度，文本保持全不透明（否则标签字看不清）
                                        color: Qt.rgba(freshColor.r, freshColor.g, freshColor.b, 0.16)
                                        Text {
                                            id: freshText
                                            anchors.centerIn: parent
                                            text: model.entry.freshness === "on_demand" ? qsTr("随机")
                                                  : model.entry.freshness === "stale" ? qsTr("可刷新")
                                                  : qsTr("最新")
                                            typography: Typography.Caption
                                            color: parent.freshColor
                                        }
                                        HoverHandler { id: freshHover }
                                        ToolTip {
                                            text: model.entry.freshness === "on_demand" ? qsTr("每次返回随机内容，可在源组头点刷新抽新")
                                                  : model.entry.freshness === "stale" ? qsTr("内容已过期，可在源组头点刷新获取最新")
                                                  : qsTr("内容为最新")
                                            visible: freshHover.hovered
                                        }
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
                        }
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
                    text: qsTr("可在「添加订阅」中加入源仓库")
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }

                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("添加订阅")
                    onClicked: root.addRepoRequested()
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
