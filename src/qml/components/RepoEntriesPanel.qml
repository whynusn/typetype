import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../helpers/SourceBadges.js" as Badges

/**
 * 开源文库条目列表面板（联邦聚合条目的统一展示）。
 *
 * 分组 / 筛选 / 搜索 / 展开状态全部在 Python 侧的 OpenLibraryListModel
 * （appBridge.openLibraryModel）：本面板只把 entries 喂给模型，再用**单个
 * ListView** 渲染扁平行（header / entry / history）。
 *
 * - 虚拟化：只实例化可视区内的行。旧结构「Column + Repeater 全量实例化每组
 *   每条」在条目多时首屏成本线性增长（2026-10-18 review P2）。
 * - 增量：展开/收起、历史切换由模型对该组做行插入/删除，其余 delegate 不动。
 * - 展开状态：用户切换过的组会记住（持久化）；没切换过的组——只有一个源
 *   时展开，多个源时收起；搜索时命中组自动展开，仍可逐组收起。
 * - 组头精简：源名 + 条目数 + 刷新 + 详情；订阅名只在多个订阅并存时显示，
 *   信任徽章只在待确认/验证失败时显示，tier 与上限细节进源详情弹窗。
 * - 随机源（rule/script/bridge）默认只显示最新一条，组尾「显示更早 N 条」。
 * - 状态叠加：加载中 / 错误(重试) / 空（引导添加订阅）/ 无匹配
 * - 选中高亮由父级通过 selectedEntry 驱动（entry_id + authority 相等判定）
 *
 * ⚠️ delegate 用 Loader 切三种行组件，组件必须声明为 Loader 的直接子项
 * （否则加载项看不到 delegate 的 model 上下文，见 AGENTS.md 陷阱）。
 */
Frame {
    id: root

    // ---- 输入 ----
    property var entries: []            // 联邦聚合的原始条目 dict
    property bool loading: false
    property string errorText: ""
    property var selectedEntry: null    // 由父级设置，用于条目高亮
    // 正在刷新的源 authority（'' = 无）：驱动「源组头」刷新动画（一份）。
    // 与 loading 分层：列表级刷新（顶部/右侧）盖整列表动画，源级刷新
    // 只在对应源组头转圈，列表保持可交互。
    property string refreshingSource: ""
    // 并发刷新集合（authority 列表）：多源同时刷新时各自组头各播一份动画
    property var refreshingSources: []
    // authority -> {state: "ok"|"failed", message, checked_at}（源健康芯片）
    property var sourceStatuses: ({})

    // ---- 输出 ----
    signal entryClicked(var entry)      // 点击条目，透传原始条目对象
    signal entryActivated(var entry)    // 双击条目：选中并直接载入跟打
    signal refreshRequested()           // 顶部刷新 / 错误态重试
    signal addRepoRequested()           // 「添加订阅」按钮（空态）
    signal subscriptionsRequested()     // 「我的订阅」：订阅级列表（含无条目的订阅）
    signal refreshSourceRequested(string authority)  // 源（authority）级刷新请求
    signal sourceInfoRequested(string authority)    // 打开源详情弹窗
    signal manageRepoRequested(string repoId, string url)  // 进入该源所属订阅源管理

    // ---- 内部 ----
    readonly property var olModel: appBridge ? appBridge.openLibraryModel : null
    property bool _filterSyncing: false  // ComboBox 模型重建去重守卫


    Layout.fillHeight: true
    Layout.fillWidth: true
    Layout.minimumWidth: 220
    radius: 6
    hoverable: false
    padding: 8

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

    // 组刷新动画判定：并发集合优先；单值属性作为旧绑定回退
    function _isRefreshingKey(key) {
        if (root.refreshingSources.length > 0)
            return root.refreshingSources.indexOf(key) !== -1
        return root.refreshingSource.length > 0 && root.refreshingSource === key
    }

    // 源健康状态（sourceStatuses 映射；不存在 = 尚未有手动刷新结果）
    function _statusOf(key) {
        return (key in root.sourceStatuses) ? root.sourceStatuses[key] : null
    }

    // 先落地尚在去抖中的搜索词：否则「清空搜索后立刻点组头」会把切换记到
    // 搜索态里，随后去抖触发、搜索态清空，这次点击就丢了
    function _flushSearch() {
        if (searchDebounce.running) {
            searchDebounce.stop()
            if (root.olModel) root.olModel.setSearch(searchField.text)
        }
    }

    function toggleGroup(key) {
        root._flushSearch()
        if (root.olModel) root.olModel.toggleGroup(key)
    }
    function toggleHistory(key) { if (root.olModel) root.olModel.toggleHistory(key) }

    // 来源筛选模型跟随 olModel.sourceLabels；保留之前选中的 label
    function rebuildSourceFilter() {
        var prev = (sourceFilterCombo.currentIndex > 0 && sourceFilterCombo.currentIndex < sourceFilterModel.count)
                   ? sourceFilterModel.get(sourceFilterCombo.currentIndex).label : ""
        var labels = root.olModel ? root.olModel.sourceLabels : []
        root._filterSyncing = true
        sourceFilterModel.clear()
        sourceFilterModel.append({ label: qsTr("全部来源") })
        var idx = 0
        for (var i = 0; i < labels.length; i++) {
            sourceFilterModel.append({ label: labels[i] })
            if (labels[i] === prev) idx = i + 1
        }
        sourceFilterCombo.currentIndex = idx
        root._filterSyncing = false
    }

    function _pushEntries() {
        if (root.olModel) root.olModel.setEntries(root.entries)
    }

    onEntriesChanged: Qt.callLater(_pushEntries)
    Component.onCompleted: { _pushEntries(); rebuildSourceFilter() }

    Connections {
        target: root.olModel
        function onSourceLabelsChanged() { root.rebuildSourceFilter() }
    }


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
                Layout.minimumWidth: 0
                typography: Typography.BodyStrong
                text: qsTr("开源文本")
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                running: root.loading
                visible: running
            }

            Item { Layout.fillWidth: true }

            // 订阅级入口：待信任 / 失败 / 已禁用 / 空源的订阅没有条目组，
            // 只能在这里看到和管理（添加订阅也在其中）
            Button {
                objectName: "repoSubscriptionsButton"
                text: qsTr("我的订阅")
                icon.name: "ic_fluent_settings_20_regular"
                flat: true
                onClicked: root.subscriptionsRequested()
            }

            ToolButton {
                objectName: "repoRefreshAll"
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
                    if (root.olModel)
                        root.olModel.setSourceFilter((currentIndex > 0 && currentIndex < sourceFilterModel.count)
                                                     ? sourceFilterModel.get(currentIndex).label : "")
                }
            }

            TextField {
                id: searchField
                objectName: "repoSearchField"
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                placeholderText: qsTr("搜索标题或预览")
                // 去抖：搜索变化 = 模型整表 reset，200ms 合并连续输入
                onTextChanged: {
                    searchDebounce.restart()
                }

                Timer {
                    id: searchDebounce
                    interval: 200
                    onTriggered: if (root.olModel) root.olModel.setSearch(searchField.text)
                }
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
            ListView {
                id: groupList
                objectName: "repoGroupList"
                anchors.fill: parent
                clip: true
                model: root.olModel
                spacing: 0
                reuseItems: false
                boundsBehavior: Flickable.StopAtBounds
                visible: !root.loading && root.errorText.length === 0 && count > 0
                QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }

                // 展开/收起：后续行位移平滑（插入行不做 opacity 入场——
                // 动画未跑完前行 opacity=0，被 ui-probe 与辅助功能视为不可见）
                displaced: Transition {
                    NumberAnimation { property: "y"
                        duration: Utils.animationDuration(Utils.animationSpeed); easing.type: Easing.OutQuint }
                }

                delegate: Loader {
                    id: rowLoader
                    width: groupList.width
                    // header 行之间留组间距（第一组除外）
                    readonly property real topGap: (model.kind === "header" && index > 0) ? 8 : 0
                    height: item ? item.height : 0
                    sourceComponent: model.kind === "header" ? headerComp
                                   : model.kind === "entry" ? entryComp
                                   : historyComp

                    // ================= 组头 =================
                    Component {
                        id: headerComp

                        Item {
                            width: rowLoader.width
                            height: rowLoader.topGap + headerRect.height

                            Rectangle {
                                id: headerRect
                                // 验收锚点（ui-probe 场景按 objectName + groupKey 定位）
                                objectName: "repoGroupHeader"
                                readonly property string groupKey: model.groupKey
                                readonly property bool groupExpanded: model.expanded
                                readonly property var status: root._statusOf(model.groupKey)
                                readonly property bool refreshing: root._isRefreshingKey(model.groupKey)
                                y: rowLoader.topGap
                                width: parent.width
                                height: model.subtitle.length > 0 || (status !== null && status.state === "failed") ? 46 : 38
                                radius: 6
                                color: headerHover.containsMouse
                                       ? Theme.currentTheme.colors.subtleSecondaryColor
                                       : Theme.currentTheme.colors.controlColor
                                border.color: Theme.currentTheme.colors.cardBorderColor
                                border.width: 1
                                Behavior on color {
                                    ColorAnimation {
                                        duration: Utils.animationDuration(Utils.appearanceSpeed)
                                        easing.type: Easing.OutQuad
                                    }
                                }

                                // 整行点击 = 展开/收起（按钮子项位于其上方优先响应）
                                MouseArea {
                                    id: headerHover
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    hoverEnabled: true
                                    onClicked: root.toggleGroup(model.groupKey)
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
                                        icon: "ic_fluent_chevron_right_20_regular"
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        transform: Rotation {
                                            angle: headerRect.groupExpanded ? 90 : 0
                                            origin.x: 8
                                            origin.y: 8
                                            Behavior on angle {
                                                NumberAnimation {
                                                    duration: Utils.animationDuration(Utils.animationSpeed)
                                                    easing.type: Easing.OutQuint
                                                }
                                            }
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        spacing: 0

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6

                                            Text {
                                                Layout.fillWidth: true
                                                Layout.minimumWidth: 0
                                                text: model.name
                                                typography: Typography.BodyStrong
                                                color: Theme.currentTheme.colors.textColor
                                                wrapMode: Text.NoWrap
                                                elide: Text.ElideRight
                                                HoverHandler { id: groupNameHover }
                                                ToolTip {
                                                    text: model.subtitle.length > 0
                                                          ? model.name + " · " + model.subtitle : model.name
                                                    visible: groupNameHover.hovered
                                                }
                                            }

                                            // 信任徽章只在需要注意时出现（待确认 / 验证失败）
                                            Rectangle {
                                                visible: model.trustState === "pending" || model.trustState === "failed"
                                                Layout.preferredWidth: trustBadgeText.implicitWidth + 8
                                                Layout.preferredHeight: 16
                                                radius: 8
                                                readonly property color trustColor:
                                                    Badges.trustColor(model.trustState, Theme.currentTheme.colors)
                                                color: Qt.rgba(trustColor.r, trustColor.g, trustColor.b, 0.16)
                                                Text {
                                                    id: trustBadgeText
                                                    anchors.centerIn: parent
                                                    text: Badges.trustLabel(model.trustState)
                                                    typography: Typography.Caption
                                                    color: parent.trustColor
                                                }
                                            }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            visible: model.subtitle.length > 0
                                                     || (headerRect.status !== null && headerRect.status.state === "failed")

                                            // 所属订阅：仅在多个订阅并存时显示（模型给空串即隐藏）
                                            Text {
                                                Layout.fillWidth: true
                                                Layout.minimumWidth: 0
                                                visible: model.subtitle.length > 0
                                                text: model.subtitle
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.textSecondaryColor
                                                wrapMode: Text.NoWrap
                                                elide: Text.ElideRight
                                            }

                                            // 源级健康芯片：失败时明确「正在显示缓存」，不盖整列表
                                            Rectangle {
                                                visible: headerRect.status !== null && headerRect.status.state === "failed"
                                                Layout.preferredHeight: 16
                                                Layout.preferredWidth: failText.implicitWidth + 10
                                                radius: 8
                                                color: Qt.rgba(Theme.currentTheme.colors.systemCautionColor.r,
                                                               Theme.currentTheme.colors.systemCautionColor.g,
                                                               Theme.currentTheme.colors.systemCautionColor.b, 0.18)
                                                Text {
                                                    id: failText
                                                    objectName: "repoGroupFailed"
                                                    anchors.centerIn: parent
                                                    text: qsTr("刷新失败 · 显示缓存")
                                                    typography: Typography.Caption
                                                    color: Theme.currentTheme.colors.systemCautionColor
                                                }
                                                ToolTip {
                                                    text: (headerRect.status && headerRect.status.message)
                                                          ? headerRect.status.message : qsTr("上次刷新失败，正在显示缓存快照")
                                                    visible: failHover.hovered
                                                }
                                                HoverHandler { id: failHover }
                                            }
                                            Item { Layout.fillWidth: model.subtitle.length === 0 }
                                        }
                                    }

                                    // 条目数：只在接近/超过仓库声明上限时带出上限（琥珀/红）
                                    Text {
                                        visible: root.width >= 300
                                        readonly property int cnt: model.count
                                        readonly property int maxN: model.maxEntries
                                        readonly property bool nearMax: maxN > 0 && cnt / maxN >= 0.8
                                        text: nearMax ? qsTr("%1 / %2 条").arg(cnt).arg(maxN) : qsTr("%1 条").arg(cnt)
                                        typography: Typography.Caption
                                        wrapMode: Text.NoWrap
                                        color: maxN > 0 && cnt > maxN ? Theme.currentTheme.colors.systemCriticalColor
                                               : nearMax ? Theme.currentTheme.colors.systemCautionColor
                                               : Theme.currentTheme.colors.textSecondaryColor
                                        HoverHandler { id: countHover }
                                        ToolTip {
                                            text: parent.maxN > 0
                                                  ? qsTr("当前缓存 %1 条，仓库声明上限 %2 条").arg(parent.cnt).arg(parent.maxN)
                                                  : qsTr("当前缓存 %1 条").arg(parent.cnt)
                                            visible: countHover.hovered
                                        }
                                    }

                                    // 源级刷新：按钮与 BusyIndicator 叠放（opacity 切换），不闪跳
                                    Item {
                                        Layout.preferredWidth: 28
                                        Layout.preferredHeight: 28

                                        ToolButton {
                                            objectName: "repoGroupRefresh"
                                            readonly property string groupKey: model.groupKey
                                            anchors.fill: parent
                                            icon.name: "ic_fluent_arrow_sync_20_regular"
                                            flat: true
                                            opacity: headerRect.refreshing ? 0 : 1
                                            enabled: !headerRect.refreshing && !root.loading
                                            Behavior on opacity {
                                                NumberAnimation {
                                                    duration: Utils.animationDuration(Utils.animationSpeedFaster)
                                                }
                                            }
                                            onClicked: root.refreshSourceRequested(model.groupKey)
                                            ToolTip {
                                                text: model.sourceType === "ott-instance"
                                                      ? qsTr("检查更新（内容未变不刷新时间）")
                                                      : qsTr("刷新该源")
                                                visible: parent.hovered
                                            }
                                        }
                                        BusyIndicator {
                                            anchors.centerIn: parent
                                            width: 16
                                            height: 16
                                            running: headerRect.refreshing
                                            visible: running
                                        }
                                    }

                                    // 源详情（类型/健康/调度覆盖 + 所属订阅管理）
                                    ToolButton {
                                        objectName: "repoGroupInfoButton"
                                        Layout.preferredWidth: 28
                                        Layout.preferredHeight: 28
                                        icon.name: "ic_fluent_info_20_regular"
                                        flat: true
                                        onClicked: root.sourceInfoRequested(model.groupKey)
                                        ToolTip { text: qsTr("源详情与订阅管理"); visible: parent.hovered }
                                    }
                                }
                            }
                        }
                    }

                    // ================= 条目行（自绘，仿本地文库 ListViewDelegate 样式） =================
                    Component {
                        id: entryComp

                        Rectangle {
                            id: rowRoot
                            objectName: "repoEntryRow"
                            readonly property var entry: model.entry
                            readonly property string entryId: model.entryId
                            readonly property string groupKey: model.groupKey
                            readonly property bool rowSelected: root._isSelected(rowRoot.entry)
                            width: rowLoader.width
                            height: rowLayout.implicitHeight + 12
                            color: (rowMouse.containsMouse && !rowRoot.rowSelected)
                                   ? Theme.currentTheme.colors.subtleSecondaryColor
                                   : (rowRoot.rowSelected
                                      ? Theme.currentTheme.colors.subtleTertiaryColor
                                      : "transparent")
                            Behavior on color {
                                ColorAnimation {
                                    duration: Utils.animationDuration(Utils.appearanceSpeed)
                                    easing.type: Easing.OutQuad
                                }
                            }

                            RowLayout {
                                id: rowLayout
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 18
                                anchors.rightMargin: 14
                                spacing: 8

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        typography: Typography.Body
                                        text: rowRoot.entry.title || rowRoot.entry.entry_id || ""
                                        color: Theme.currentTheme.colors.textColor
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideRight
                                        HoverHandler { id: entryTitleHover }
                                        ToolTip {
                                            text: rowRoot.entry.title || rowRoot.entry.entry_id || ""
                                            visible: entryTitleHover.hovered
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: root.entryPreview(rowRoot.entry)
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                        visible: text.length > 0
                                    }
                                }

                                ColumnLayout {
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.minimumWidth: 0
                                    Layout.maximumWidth: 132
                                    Layout.preferredWidth: 112
                                    spacing: 3

                                    RowLayout {
                                        Layout.alignment: Qt.AlignRight
                                        spacing: 4

                                        Rectangle {
                                            visible: rowRoot.entry.content_mode === "segmented"
                                            Layout.preferredWidth: segBadgeText.implicitWidth + 10
                                            Layout.preferredHeight: 18
                                            radius: 9
                                            color: Qt.rgba(Theme.currentTheme.colors.systemCautionColor.r,
                                                           Theme.currentTheme.colors.systemCautionColor.g,
                                                           Theme.currentTheme.colors.systemCautionColor.b, 0.16)
                                            Text {
                                                id: segBadgeText
                                                anchors.centerIn: parent
                                                text: qsTr("分段")
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.systemCautionColor
                                            }
                                        }

                                        // 新鲜度（on_demand 随机 / stale 可刷新 / fresh 最新）
                                        Rectangle {
                                            readonly property string fr: rowRoot.entry.freshness || ""
                                            visible: fr !== ""
                                            Layout.preferredWidth: freshBadgeText.implicitWidth + 12
                                            Layout.preferredHeight: 18
                                            radius: 9
                                            readonly property color freshColor:
                                                fr === "on_demand" ? Theme.currentTheme.colors.primaryColor
                                                : fr === "stale" ? Theme.currentTheme.colors.systemCautionColor
                                                : Theme.currentTheme.colors.systemSuccessColor
                                            color: Qt.rgba(freshColor.r, freshColor.g, freshColor.b, 0.16)
                                            Text {
                                                id: freshBadgeText
                                                anchors.centerIn: parent
                                                text: parent.fr === "on_demand" ? qsTr("随机")
                                                      : parent.fr === "stale" ? qsTr("可刷新")
                                                      : qsTr("最新")
                                                typography: Typography.Caption
                                                color: parent.freshColor
                                            }
                                            HoverHandler { id: freshHover }
                                            ToolTip {
                                                text: parent.fr === "on_demand"
                                                      ? qsTr("每次返回随机内容，可在源组头点刷新抽新")
                                                      : parent.fr === "stale"
                                                        ? qsTr("内容已过期，可在源组头点刷新获取最新")
                                                        : qsTr("内容为最新")
                                                visible: freshHover.hovered
                                            }
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        Layout.alignment: Qt.AlignRight
                                        visible: text.length > 0
                                        text: {
                                            var suffix = ""
                                            if (rowRoot.entry.checked_without_change === true)
                                                suffix = " · " + qsTr("刚检查，内容无变化")
                                            else if (rowRoot.entry.last_fetched_relative)
                                                suffix = " · " + qsTr("内容 %1").arg(rowRoot.entry.last_fetched_relative)
                                            var count = root._charCount(rowRoot.entry)
                                            return count > 0 ? (count + " 字" + suffix) : suffix
                                        }
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideLeft
                                    }
                                }
                            }

                            MouseArea {
                                id: rowMouse
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: root.entryClicked(rowRoot.entry)
                                onDoubleClicked: root.entryActivated(rowRoot.entry)
                            }

                            // 选中指示条（左竖条，仿本地文库 Indicator）
                            Rectangle {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: parent.height - 14
                                radius: 1.5
                                color: Theme.currentTheme.colors.primaryColor
                                visible: rowRoot.rowSelected
                            }
                        }
                    }

                    // ================= 历史行：「显示更早 N 条」/「收起历史」 =================
                    Component {
                        id: historyComp

                        Rectangle {
                            id: historyRow
                            objectName: "repoHistoryToggle"
                            readonly property string groupKey: model.groupKey
                            readonly property bool collapseMode: model.historyExpanded
                            width: rowLoader.width
                            height: 36
                            color: historyMouse.containsMouse
                                   ? Theme.currentTheme.colors.subtleSecondaryColor
                                   : "transparent"

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.leftMargin: 18
                                anchors.rightMargin: 18
                                height: 1
                                color: Theme.currentTheme.colors.cardBorderColor
                            }

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 6

                                Text {
                                    text: historyRow.collapseMode
                                          ? qsTr("收起历史")
                                          : qsTr("显示更早 %1 条").arg(model.historyCount)
                                    typography: Typography.Caption
                                    color: Theme.currentTheme.colors.primaryColor
                                }

                                IconWidget {
                                    Layout.preferredWidth: 12
                                    Layout.preferredHeight: 12
                                    icon: historyRow.collapseMode
                                          ? "ic_fluent_chevron_up_20_regular"
                                          : "ic_fluent_chevron_down_20_regular"
                                    color: Theme.currentTheme.colors.primaryColor
                                }
                            }

                            MouseArea {
                                id: historyMouse
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: root.toggleHistory(model.groupKey)
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
                         && root.entries.length === 0

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

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8
                    Button {
                        text: qsTr("添加订阅")
                        onClicked: root.addRepoRequested()
                    }
                    // 有订阅但全部禁用 / 待信任 / 拉取失败时，空态也要能进管理
                    Button {
                        text: qsTr("我的订阅")
                        flat: true
                        onClicked: root.subscriptionsRequested()
                    }
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
                         && groupList.count === 0 && root.entries.length > 0
            }
        }
    }
}
