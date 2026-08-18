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
 * - 组头可展开/收起（_expanded 状态；**默认收起**；展开/收起带高度
 *   动画——每组是「组头卡片 + 高度动画内容区 + 内层 ListView」结构）
 * - 组内条目为**连续无间隔列表**，样式与本地文库一致（RinUI
 *   ListViewDelegate：subtle 背景 + 悬停高亮 + 选中指示条，无独立卡片边框），
 *   与组头的矩形卡片形成层级区分
 * - 随机源（rule/script/bridge）默认只显示最新一条；组内列表底部提供
 *   「显示更早 N 条」行展开历史（快照保留最近 N 条，历史可重载重打；
 *   历史入口在列表底部而非组头按钮，更符合连续列表直觉）
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
    signal refreshRequested()           // 顶部刷新 / 错误态重试
    signal addRepoRequested()           // 「添加订阅」按钮
    signal refreshSourceRequested(string authority)  // 源（authority）级刷新请求
    signal sourceInfoRequested(string authority)    // 打开源详情弹窗
    signal manageRepoRequested(string repoId, string url)  // 进入该源所属订阅源管理

    // ---- 内部 ----
    property string selectedSourceLabel: ""
    property bool _filterSyncing: false  // ComboBox 模型重建去重守卫
    // 组展开状态（key = authority；**缺省收起**：undefined/false = 收起，true = 展开）
    property var _expanded: ({})
    // 随机源历史展开状态（key = authority；缺省只显示最新一条）
    property var _showHistory: ({})
    // 展开/历史切换版本号：QML 无法追踪 var 字典的内部变化，每次切换递增，
    // 驱动外层 delegate 的 expanded 绑定与内层行模型重算（见 toggleGroup）
    property int _innerVersion: 0

    Layout.fillHeight: true
    Layout.fillWidth: true
    Layout.minimumWidth: 220
    radius: 6
    hoverable: false
    padding: 8

    // 组名回退：_source_label（manifest source.label 注入）缺失时用条目
    // source_label 原文。展示名一律来自上游 manifest 声明——这里不硬编码
    // 任何中文映射（曾把 source_label 硬映射成「一言/极速杯/英文名言/
    // 今日诗词」，存量快照缺字段时会把同一订阅源拆成多个假源组）。
    function sourceDisplayName(entry) {
        return entry.source_label || qsTr("开源文本")
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

    // 组刷新动画判定：该组（authority）正在被刷新 → 组头播放一份动画。
    // 优先使用并发集合；单值属性作为旧绑定回退。
    function _isRefreshingGroup(group) {
        if (!group) return false
        var key = group.key || ""
        if (root.refreshingSources.length > 0)
            return root.refreshingSources.indexOf(key) !== -1
        return root.refreshingSource.length > 0 && root.refreshingSource === key
    }

    // 源健康状态（sourceStatuses 映射；不存在 = 尚未有手动刷新结果）
    function _groupStatus(group) {
        if (!group || !(group.key in root.sourceStatuses)) return null
        return root.sourceStatuses[group.key]
    }

    function _tierShort(type) {
        if (type === "ott-instance") return "L0"
        if (type === "ott-rule") return "L1"
        if (type === "ott-bridge") return "L2"
        if (type === "ott-script") return "L3"
        return ""
    }

    function _trustLabel(state) {
        if (state === "verified") return qsTr("已验证")
        if (state === "pending") return qsTr("待确认")
        if (state === "failed") return qsTr("验证失败")
        if (state === "unverified") return qsTr("未验证")
        return ""
    }

    function _matches(entry, text) {
        var haystack = (entry.title || "") + " " +
                       (entry._source_label || entry.source_label || "") + " " +
                       (entry.category || "") + " " +
                       ((entry.tags || []).join(" ")) + " " +
                       root.entryPreview(entry)
        return haystack.toLowerCase().indexOf(text) !== -1
    }

    function isOnDemandSource(type) {
        return type === "ott-rule" || type === "ott-script" || type === "ott-bridge"
    }

    // 组头展开/收起切换（缺省收起）。注意：只翻转状态 + 递增版本号，
    // **不再重建外层模型**——delegate 的 expanded 绑定与内容区高度
    // Behavior 负责平滑动画；_innerVersion 是 QML var 字典的内部变化
    // 通知机制（字典键赋值不触发属性通知）。
    function toggleGroup(key) {
        root._expanded[key] = !(root._expanded[key] === true)
        root._innerVersion++
    }

    // 随机源历史：默认只显示最新一条；切换后内层行模型重算
    // （历史入口是组内列表底部的「显示更早 N 条」行）
    function toggleHistory(key) {
        root._showHistory[key] = !(root._showHistory[key] === true)
        root._innerVersion++
    }

    // 填充某个组的内层 ListModel（只存条目行；普通源全部条目，随机源
    // 默认仅最新一条——历史由组 delegate 底部的独立「显示更早 N 条」行
    // 承载，见 groupDelegate.showHistoryRow）。
    //
    // ⚠️ 不用 JS 数组当模型：实测本环境（Qt 6.10.2/PySide6）JS 数组作为
    // ListView model 时 delegate 里 model.<role> 全部解析为 undefined
    // （数组整体暴露而非元素对象），ListModel 的 role 访问正常——统一
    // 走 ListModel。
    // 调用方：组 delegate 的 Component.onCompleted 与 root._innerVersion
    // 变化（Connections onInnerVersionChanged，toggleGroup/toggleHistory
    // 递增版本号驱动）。
    function fillInnerModel(m, group) {
        m.clear()
        if (!group) return
        var entries = group.entries || []
        var showAll = !group.onDemand || root._showHistory[group.key] === true
        for (var j = 0; j < entries.length; j++) {
            if (!showAll && j > 0) break
            m.append({ entry: entries[j] })
        }
    }

    // 按源（authority）动态分组重建外层模型：每组一行（组头 + 展开内容）。
    // 筛选/搜索作用于条目，空组不渲染。
    //
    // 分组语义（2026-08-15）：列表精度到**每一条规则/源**（authority 级，
    // federation 注入 _source_label/_source_type）；订阅源（repo）只作
    // 标识显示在组头副标题（_repo_name），本身不出现在列表中。
    //
    // 两遍构建：旧实现单遍遍历 entries，组头在遇到组内第一条时插入、
    // 后续同组条目 append 到模型末尾——当同组条目在 entries 中不连续
    // （随机源多次物化、新旧条目按 captured_at 交错）时，后到的条目会
    // 被追加到别的组头之后（实测 jisubei 的条目跑到「英文名言」组下）。
    // 先收集有序组 + 组内条目，再按组顺序整组输出，保证组内条目连续。
    function rebuild() {
        listModel.clear()
        var t = searchField.text.trim().toLowerCase()
        var filterLabel = root.selectedSourceLabel
        var groups = []      // 有序组列表（按第一条目出现顺序）
        var groupAt = {}     // group key -> groups 数组下标
        for (var i = 0; i < root.entries.length; i++) {
            var e = root.entries[i]
            var entryLabel = e._source_label || e.source_label || ""
            if (filterLabel.length > 0 && entryLabel !== filterLabel) continue
            if (t.length > 0 && !root._matches(e, t)) continue
            // 动态分组键：源（authority）级——每条规则/源一个组
            var key = e._authority || e.authority || ""
            if (groupAt[key] === undefined) {
                groupAt[key] = groups.length
                groups.push({
                    key: key,
                    name: e._source_label || e.source_label || root.sourceDisplayName(e),
                    // 所属订阅源标识（repo 名；缺失回退 URL 原文，再回退 key）
                    subtitle: e._repo_name || e._repo_url || key,
                    repoId: e._repo_id || "",
                    sourceType: e._source_type || "",
                    trustState: e._repo_trust_state || "",
                    onDemand: root.isOnDemandSource(e._source_type || ""),
                    url: e._repo_url || "",
                    maxEntries: e._repo_max_entries || 0,
                    entries: []
                })
            }
            groups[groupAt[key]].entries.push(e)
        }
        for (var g = 0; g < groups.length; g++) {
            groups[g].count = groups[g].entries.length   // 组头计数（N / M 条）
            listModel.append({ group: groups[g] })
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
            var label = root.entries[i]._source_label || root.entries[i].source_label || ""
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

                // ⚠️ 根本方案：组列表同样不用 ListView（delegate 复用/高度计算
                // 时序/虚拟化重建等隐式行为）——Column + Repeater 全量实例化，
                // 组高度 = 组头 + 内容区高度，由 Column 布局器排布，可靠。
                Column {
                    id: groupsColumn
                    width: parent.width
                    height: implicitHeight      // 显式几何高度（Flickable 滚动依赖）
                    spacing: 8                  // 组（卡片）之间留间隔

                    Repeater {
                        model: ListModel { id: listModel }

                        // ============ 组 delegate：组头卡片 + 动画内容区 ============
                        delegate: Item {
                            id: groupDelegate
                            width: groupsColumn.width
                            height: headerRect.height + contentClip.height

                        // 承接外层模型行数据：内层 ListView 自身也有 model 属性，
                        // 在其属性绑定里裸引用 model 会解析到自身（undefined）——
                        // 统一经本属性 + id 访问，避免 QML 名称遮蔽坑。
                        readonly property var groupData: model.group

                        // 展开状态（缺省收起）。绑定引用 _innerVersion：
                        // toggleGroup 递增后本绑定重算，驱动内容区高度动画。
                        readonly property bool expanded: root._innerVersion >= 0
                                                         && root._expanded[groupDelegate.groupData.key] === true

                        // 历史行可见性：随机源默认只显示最新一条、且组内确有
                        // 更早条目时，在组内列表底部显示「显示更早 N 条」入口
                        // （点击展开全部历史快照，可重载重打）。绑定引用
                        // _innerVersion：toggleHistory 递增后重算。
                        readonly property bool showHistoryRow: root._innerVersion >= 0
                            && groupDelegate.groupData.onDemand
                            && root._showHistory[groupDelegate.groupData.key] !== true
                            && groupDelegate.groupData.entries.length > 1

                        // 组内行模型（ListModel；role 访问可靠——JS 数组模型
                        // 在本环境 role 全 undefined，见 fillInnerModel 注释）
                        ListModel { id: innerModel }

                        // 初始填充 + 版本号变化（toggleGroup/toggleHistory）时重建。
                        // ⚠️ 下划线属性 _innerVersion 的变化信号名保留下划线（_innerVersionChanged），
                        // QML 规范化信号处理器名：on_InnerVersionChanged
                        Component.onCompleted: root.fillInnerModel(innerModel, groupDelegate.groupData)
                        Connections {
                            target: root
                            function on_InnerVersionChanged() {
                                root.fillInnerModel(innerModel, groupDelegate.groupData)
                            }
                        }

                        // ================= 组头：订阅源卡片 =================
                        Rectangle {
                            id: headerRect
                            width: parent.width
                            height: 46
                            radius: 6
                            color: headerHover.containsMouse
                                   ? Theme.currentTheme.colors.subtleSecondaryColor
                                   : Theme.currentTheme.colors.controlColor
                            border.color: Theme.currentTheme.colors.cardBorderColor
                            border.width: 1
                            Behavior on color {
                                ColorAnimation { duration: Utils.appearanceSpeed; easing.type: Easing.OutQuad }
                            }

                            // 整行点击 = 展开/收起（按钮子项位于其上方优先响应）
                            MouseArea {
                                id: headerHover
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: root.toggleGroup(groupDelegate.groupData.key)
                            }

                            RowLayout {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                spacing: 8

                                // 展开指示：chevron 旋转动画（RinUI Expander 同款）
                                IconWidget {
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    icon: "ic_fluent_chevron_right_20_regular"
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    transform: Rotation {
                                        id: chevronRot
                                        angle: groupDelegate.expanded ? 90 : 0
                                        origin.x: 8
                                        origin.y: 8
                                        Behavior on angle {
                                            NumberAnimation { duration: Utils.animationSpeed; easing.type: Easing.OutQuint }
                                        }
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Text {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: groupDelegate.groupData.name
                                            typography: Typography.BodyStrong
                                            color: Theme.currentTheme.colors.textColor
                                            wrapMode: Text.NoWrap
                                            elide: Text.ElideRight
                                            HoverHandler { id: groupNameHover }
                                            ToolTip {
                                                text: groupDelegate.groupData.name
                                                visible: groupNameHover.hovered
                                            }
                                        }

                                        Rectangle {
                                            visible: root._tierShort(groupDelegate.groupData.sourceType).length > 0
                                            Layout.preferredWidth: tierBadgeText.implicitWidth + 8
                                            Layout.preferredHeight: 16
                                            radius: 8
                                            color: Theme.currentTheme.colors.controlColor
                                            Text {
                                                id: tierBadgeText
                                                anchors.centerIn: parent
                                                text: root._tierShort(groupDelegate.groupData.sourceType)
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.textAccentColor
                                            }
                                        }

                                        Rectangle {
                                            visible: root._trustLabel(groupDelegate.groupData.trustState).length > 0
                                            Layout.preferredWidth: trustBadgeText.implicitWidth + 8
                                            Layout.preferredHeight: 16
                                            radius: 8
                                            readonly property color trustColor:
                                                groupDelegate.groupData.trustState === "verified"
                                                    ? Theme.currentTheme.colors.systemSuccessColor
                                                    : groupDelegate.groupData.trustState === "pending"
                                                      ? Theme.currentTheme.colors.systemCautionColor
                                                      : groupDelegate.groupData.trustState === "failed"
                                                        ? Theme.currentTheme.colors.systemCriticalColor
                                                        : Theme.currentTheme.colors.textSecondaryColor
                                            color: Qt.rgba(trustColor.r, trustColor.g, trustColor.b, 0.16)
                                            Text {
                                                id: trustBadgeText
                                                anchors.centerIn: parent
                                                text: root._trustLabel(groupDelegate.groupData.trustState)
                                                typography: Typography.Caption
                                                color: parent.trustColor
                                            }
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Text {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            text: groupDelegate.groupData.subtitle
                                            typography: Typography.Caption
                                            color: Theme.currentTheme.colors.textSecondaryColor
                                            wrapMode: Text.NoWrap
                                            elide: Text.ElideRight
                                            HoverHandler { id: subtitleHover }
                                            ToolTip {
                                                text: groupDelegate.groupData.subtitle
                                                visible: subtitleHover.hovered
                                            }
                                        }

                                        // 源级健康芯片：失败时明确「正在显示缓存」，不盖整列表
                                        Rectangle {
                                            readonly property var status: root._groupStatus(groupDelegate.groupData)
                                            visible: status !== null && status.state === "failed"
                                            Layout.preferredHeight: 16
                                            Layout.preferredWidth: failText.implicitWidth + 10
                                            radius: 8
                                            color: Qt.rgba(Theme.currentTheme.colors.systemCautionColor.r,
                                                           Theme.currentTheme.colors.systemCautionColor.g,
                                                           Theme.currentTheme.colors.systemCautionColor.b, 0.18)
                                            Text {
                                                id: failText
                                                anchors.centerIn: parent
                                                text: qsTr("刷新失败 · 显示缓存")
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.systemCautionColor
                                            }
                                            ToolTip {
                                                text: (parent.status && parent.status.message)
                                                      ? parent.status.message : qsTr("上次刷新失败，正在显示缓存快照")
                                                visible: failMouse.hovered
                                            }
                                            HoverHandler { id: failMouse }
                                        }
                                    }
                                }

                                // 文本计数 + 上限进度：manifest 声明 max_entries 时
                                // 显示「N / M 条」+ 细进度条（接近上限转琥珀、满格绿）；
                                // 未声明（M=0 = 无上限）只显示当前数。
                                // 注意：M 是仓库声明的条目保留上限，而 N 是当前该源已缓存的快照数。
                                ColumnLayout {
                                    visible: root.width >= 300
                                    spacing: 2
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.minimumWidth: 0
                                    Layout.preferredWidth: 88

                                    Text {
                                        Layout.alignment: Qt.AlignRight
                                        text: {
                                            var count = groupDelegate.groupData.count
                                            var maxEntries = groupDelegate.groupData.maxEntries
                                            var s = qsTr("%1 条").arg(count)
                                            if (maxEntries > 0) {
                                                if (count > maxEntries)
                                                    s = qsTr("%1 条（超上限 %2）").arg(count).arg(maxEntries)
                                                else
                                                    s = qsTr("%1 / %2 条").arg(count).arg(maxEntries)
                                            }
                                            return s
                                        }
                                        wrapMode: Text.NoWrap
                                        typography: Typography.Caption
                                        color: groupDelegate.groupData.maxEntries > 0
                                               && groupDelegate.groupData.count / groupDelegate.groupData.maxEntries >= 0.8
                                               && groupDelegate.groupData.count > groupDelegate.groupData.maxEntries
                                               ? Theme.currentTheme.colors.systemCriticalColor
                                               : (groupDelegate.groupData.maxEntries > 0
                                                  && groupDelegate.groupData.count / groupDelegate.groupData.maxEntries >= 0.8
                                                  ? Theme.currentTheme.colors.systemCautionColor
                                                  : Theme.currentTheme.colors.textSecondaryColor)

                                        HoverHandler { id: countHover }
                                        ToolTip {
                                            text: groupDelegate.groupData.maxEntries > 0
                                                  ? qsTr("当前缓存 %1 条，仓库声明上限 %2 条").arg(groupDelegate.groupData.count).arg(groupDelegate.groupData.maxEntries)
                                                  : qsTr("当前缓存 %1 条").arg(groupDelegate.groupData.count)
                                            visible: countHover.hovered
                                        }
                                    }

                                    // 上限进度条（仅声明上限时显示）
                                    Rectangle {
                                        visible: groupDelegate.groupData.maxEntries > 0
                                        Layout.alignment: Qt.AlignRight
                                        Layout.preferredWidth: 52
                                        Layout.preferredHeight: 3
                                        radius: 1.5
                                        color: Theme.currentTheme.colors.controlColor

                                        Rectangle {
                                            readonly property real ratio: groupDelegate.groupData.maxEntries > 0
                                                ? Math.min(1, groupDelegate.groupData.count / groupDelegate.groupData.maxEntries)
                                                : 0
                                            width: parent.width * ratio
                                            height: parent.height
                                            radius: 1.5
                                            color: groupDelegate.groupData.maxEntries > 0
                                                   && groupDelegate.groupData.count > groupDelegate.groupData.maxEntries
                                                   ? Theme.currentTheme.colors.systemCriticalColor
                                                   : (ratio >= 1
                                                      ? Theme.currentTheme.colors.systemSuccessColor
                                                      : (ratio >= 0.8
                                                         ? Theme.currentTheme.colors.systemCautionColor
                                                         : Theme.currentTheme.colors.primaryColor))
                                        }
                                    }
                                }

                                // 源级刷新：一个源无论多少文本，动画只在组头播放一份；
                                // 按钮与 BusyIndicator 叠放（opacity 切换），不闪跳
                                Item {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28

                                    ToolButton {
                                        anchors.fill: parent
                                        icon.name: "ic_fluent_arrow_sync_20_regular"
                                        flat: true
                                        opacity: root._isRefreshingGroup(groupDelegate.groupData) ? 0 : 1
                                        enabled: !root._isRefreshingGroup(groupDelegate.groupData) && !root.loading
                                        Behavior on opacity {
                                            NumberAnimation { duration: Utils.animationSpeedFaster }
                                        }
                                        onClicked: root.refreshSourceRequested(groupDelegate.groupData.key)
                                        ToolTip {
                                            text: groupDelegate.groupData.sourceType === "ott-instance"
                                                  ? qsTr("检查更新（内容未变不刷新时间）")
                                                  : qsTr("刷新该源")
                                            visible: parent.hovered
                                        }
                                    }
                                    BusyIndicator {
                                        anchors.centerIn: parent
                                        width: 16
                                        height: 16
                                        running: root._isRefreshingGroup(groupDelegate.groupData)
                                        visible: running
                                    }
                                }

                                // 源详情（类型/健康/调度覆盖）
                                ToolButton {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                    icon.name: "ic_fluent_info_20_regular"
                                    flat: true
                                    onClicked: root.sourceInfoRequested(groupDelegate.groupData.key)
                                    ToolTip { text: qsTr("源详情"); visible: parent.hovered }
                                }

                                // 管理该源所属订阅源（进入配置弹窗）
                                ToolButton {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                    icon.name: "ic_fluent_settings_20_regular"
                                    flat: true
                                    onClicked: root.manageRepoRequested(groupDelegate.groupData.repoId, groupDelegate.groupData.url)
                                    ToolTip { text: qsTr("管理该源所属订阅源"); visible: parent.hovered }
                                }
                            }
                        }

                        // ================= 内容区：高度动画 =================
                        // ⚠️ 根本布局方案（2026-08-16 重构）：组内条目**不用嵌套
                        // ListView + Loader + ListViewDelegate**（该组合踩遍 implicit
                        // 死锁 / Loader 不报尺寸导致行高塌缩 / ListView.view attached
                        // property 不可用等坑，用户连续三次报重叠）——改用
                        // **Column + Repeater 全量实例化**（每源条目数有限），行高度
                        // 全部由布局容器（RowLayout/ColumnLayout/Column）的 implicit
                        // 尺寸驱动，这是 QML 唯一可靠的高度计算机制：无 delegate
                        // 实例化时机、无 Loader 透传、无 attached property 依赖。
                        Rectangle {
                            id: contentClip
                            // ⚠️ 必须显式定位到组头下方：Item 内子项默认堆叠在
                            // (0,0)，不设 y 会与 headerRect 重叠（内容区盖住组头，
                            // 实测 2026-08-16：展开后条目渲染在组头位置上）。
                            // ⚠️ 必须显式透明背景：Rectangle 默认 color 是纯白
                            // #FFFFFF，展开时白色矩形盖在列表区上（暗色主题下
                            // 尤其刺眼，实测 2026-08-16 用户截图 100% 纯白块）。
                            y: headerRect.height
                            width: parent.width
                            color: "transparent"
                            clip: true
                            // 展开：完整显示条目列内容高度；收起：0。Behavior 平滑过渡
                            // （Column 的 implicitHeight 由布局器计算，可靠）
                            height: groupDelegate.expanded ? innerColumn.height : 0
                            opacity: groupDelegate.expanded ? 1 : 0

                            Behavior on height {
                                NumberAnimation {
                                    duration: Utils.animationSpeedExpander
                                    easing.type: Easing.OutQuint
                                }
                            }
                            Behavior on opacity {
                                NumberAnimation { duration: Utils.appearanceSpeed; easing.type: Easing.OutQuad }
                            }

                            // ---- 条目列：连续无间隔（spacing 0） ----
                            Column {
                                id: innerColumn
                                width: parent.width
                                spacing: 0

                                // 条目行（Repeater 全量实例化；模型只含 entry 行）
                                Repeater {
                                    model: innerModel
                                    delegate: entryRowComp
                                }

                                // ---- 历史行：随机源「显示更早 N 条」入口 ----
                                Rectangle {
                                    id: historyRow
                                    width: parent.width
                                    height: 36
                                    visible: groupDelegate.showHistoryRow
                                    color: historyMouse.containsMouse
                                           ? Theme.currentTheme.colors.subtleSecondaryColor
                                           : "transparent"
                                    Behavior on color {
                                        ColorAnimation { duration: Utils.appearanceSpeed; easing.type: Easing.OutQuad }
                                    }

                                    // 与最新条目的分隔细线
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
                                            text: qsTr("显示更早 %1 条").arg(groupDelegate.groupData.entries.length - 1)
                                            typography: Typography.Caption
                                            color: Theme.currentTheme.colors.primaryColor
                                        }

                                        IconWidget {
                                            Layout.preferredWidth: 12
                                            Layout.preferredHeight: 12
                                            icon: "ic_fluent_chevron_down_20_regular"
                                            color: Theme.currentTheme.colors.primaryColor
                                        }
                                    }

                                    MouseArea {
                                        id: historyMouse
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        hoverEnabled: true
                                        onClicked: root.toggleHistory(groupDelegate.groupData.key)
                                    }
                                }
                            }

                            // ============ 条目行组件（自绘，仿本地文库 ListViewDelegate 样式） ============
                            // ⚠️ 不复用 ListViewDelegate：其内部依赖 ListView.view attached
                            // property（本结构无 ListView）；自绘行高度 = 内部布局 implicit
                            // 尺寸 + padding，完全由布局器计算，杜绝行高塌缩。
                            Component {
                                id: entryRowComp

                                Rectangle {
                                    id: rowRoot
                                    width: parent.width
                                    // 行高由内部布局 implicit 尺寸驱动（布局容器计算可靠）
                                    height: rowLayout.implicitHeight + 12

                                    readonly property bool rowSelected: root._isSelected(model.entry)

                                    color: (rowMouse.containsMouse && !rowRoot.rowSelected)
                                           ? Theme.currentTheme.colors.subtleSecondaryColor
                                           : (rowRoot.rowSelected
                                              ? Theme.currentTheme.colors.subtleTertiaryColor
                                              : "transparent")
                                    Behavior on color {
                                        ColorAnimation { duration: Utils.appearanceSpeed; easing.type: Easing.OutQuad }
                                    }

                                    RowLayout {
                                        id: rowLayout
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.leftMargin: 18
                                        anchors.rightMargin: 14
                                        spacing: 8

                                        // 左：标题 + 2 行预览
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            Text {
                                                Layout.fillWidth: true
                                                Layout.minimumWidth: 0
                                                typography: Typography.Body
                                                text: model.entry.title || model.entry.entry_id || ""
                                                color: Theme.currentTheme.colors.textColor
                                                wrapMode: Text.NoWrap
                                                elide: Text.ElideRight
                                                HoverHandler { id: entryTitleHover }
                                                ToolTip {
                                                    text: model.entry.title || model.entry.entry_id || ""
                                                    visible: entryTitleHover.hovered
                                                }
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.textSecondaryColor
                                                text: root.entryPreview(model.entry)
                                                wrapMode: Text.Wrap
                                                maximumLineCount: 2
                                                elide: Text.ElideRight
                                                visible: text.length > 0
                                            }
                                        }

                                        // 右：徽章列（分段/新鲜度）+ 字数
                                        ColumnLayout {
                                            Layout.alignment: Qt.AlignVCenter
                                            Layout.minimumWidth: 0
                                            Layout.maximumWidth: 132
                                            Layout.preferredWidth: 112
                                            spacing: 3

                                            RowLayout {
                                                Layout.alignment: Qt.AlignRight
                                                spacing: 4

                                                // 分段徽章
                                                Rectangle {
                                                    visible: model.entry.content_mode === "segmented"
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

                                                // 新鲜度状态标签（on_demand 随机 / stale 可刷新 / fresh 最新）
                                                Rectangle {
                                                    visible: model.entry.freshness !== undefined
                                                             && model.entry.freshness !== ""
                                                    Layout.preferredWidth: freshBadgeText.implicitWidth + 12
                                                    Layout.preferredHeight: 18
                                                    radius: 9
                                                    readonly property color freshColor:
                                                        model.entry.freshness === "on_demand"
                                                            ? Theme.currentTheme.colors.primaryColor
                                                            : model.entry.freshness === "stale"
                                                              ? Theme.currentTheme.colors.systemCautionColor
                                                              : Theme.currentTheme.colors.systemSuccessColor
                                                    // 只给背景降透明度，文本保持全不透明（否则标签字看不清）
                                                    color: Qt.rgba(freshColor.r, freshColor.g, freshColor.b, 0.16)
                                                    Text {
                                                        id: freshBadgeText
                                                        anchors.centerIn: parent
                                                        text: model.entry.freshness === "on_demand" ? qsTr("随机")
                                                              : model.entry.freshness === "stale" ? qsTr("可刷新")
                                                              : qsTr("最新")
                                                        typography: Typography.Caption
                                                        color: parent.freshColor
                                                    }
                                                    HoverHandler { id: freshHover }
                                                    ToolTip {
                                                        text: model.entry.freshness === "on_demand"
                                                              ? qsTr("每次返回随机内容，可在源组头点刷新抽新")
                                                              : model.entry.freshness === "stale"
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
                                                    if (model.entry.checked_without_change === true)
                                                        suffix = " · " + qsTr("刚检查，内容无变化")
                                                    else if (model.entry.last_fetched_relative)
                                                        suffix = " · " + qsTr("内容 %1").arg(model.entry.last_fetched_relative)
                                                    var count = root._charCount(model.entry)
                                                    return count > 0 ? (count + " 字" + suffix) : suffix
                                                }
                                                typography: Typography.Caption
                                                color: Theme.currentTheme.colors.textSecondaryColor
                                                wrapMode: Text.NoWrap
                                                elide: Text.ElideLeft
                                            }
                                        }
                                    }

                                    // 整行点击（RowLayout 纯布局不接收鼠标，事件穿透到此）
                                    MouseArea {
                                        id: rowMouse
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        hoverEnabled: true
                                        onClicked: root.entryClicked(model.entry)
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
