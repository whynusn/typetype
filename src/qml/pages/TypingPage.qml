import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../typing"
import "../components"

Item {
    id: typingPage
    property bool active: false  // 由 NavigationView 注入
    property bool loggedin: false  // Will be injected by NavigationView
    property bool showLeaderboard: false
    property string sliceStatusText: ""
    property string sliceCriteriaText: ""
    property string currentZitiHint: ""
    readonly property int historyMaxRows: 200

    //=====================================
    // 函数
    //=====================================

    function handleRetypeRequest() {
        lowerPane.suppressTextChanged = true;
        lowerPane.text = "";
        lowerPane.suppressTextChanged = false;
        if (appBridge)
            appBridge.handleLoadedText(upperPane.textDocument, upperPane.text);
        Qt.callLater(function() {
            lowerPane.lastText = lowerPane.text;
        });
    }

    function applyLoadedText(plainText) {
        lowerPane.suppressTextChanged = true;
        lowerPane.text = "";
        lowerPane.suppressTextChanged = false;
        upperPane.text = plainText;
        appBridge.handleLoadedText(upperPane.textDocument, plainText);
        upperPane.setCursorAndScroll(0, true);
        // handleLoadedText 完成后，延迟到当前事件循环末尾再同步 lastText。
        // 这样可以捕获所有异步 onTextChanged 事件（如 IME preedit 清除），
        // 确保 lastText 始终与 lowerPane.text 一致。
        Qt.callLater(function() {
            lowerPane.lastText = lowerPane.text;
        });
    }

    function syncSliceStatus() {
        typingPage.sliceStatusText = appBridge ? appBridge.getSliceStatus() : "";
    }

    function syncSliceCriteria() {
        typingPage.sliceCriteriaText = appBridge ? appBridge.getSliceCriteria() : "";
    }

    function openSliceConfig() {
        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("CustomLoadTextPage.qml"));
        }
    }

    function refreshZitiHint() {
        if (!appBridge || !appBridge.zitiEnabled) {
            typingPage.currentZitiHint = "";
            return;
        }
        var pos = appBridge.getCursorPos();
        var ch = pos >= 0 && pos < upperPane.text.length ? upperPane.text.charAt(pos) : "";
        typingPage.currentZitiHint = ch ? appBridge.getZitiHint(ch) : "";
    }

    function sliceStatusPrimaryText() {
        var parts = typingPage.sliceStatusText.split("  |  ");
        return parts.length > 0 ? parts[0] : "";
    }

    function sliceStatusSecondaryText() {
        var parts = typingPage.sliceStatusText.split("  |  ");
        return parts.length > 1 ? parts[1] : "";
    }

    function triggerRandomWenlaiText() {
        if (appBridge && appBridge.wenlaiLoading)
            return;
        if (appBridge)
            appBridge.loadRandomWenlaiText();
    }

    function triggerPrevSegment() {
        if (appBridge && appBridge.wenlaiLoading)
            return;
        if (appBridge) {
            if (appBridge.isWenlaiActive && !appBridge.sliceMode) {
                appBridge.loadPrevWenlaiSegment();
            } else {
                appBridge.loadPrevSlice();
            }
        }
    }

    function triggerNextSegment() {
        if (appBridge && appBridge.wenlaiLoading)
            return;
        if (appBridge) {
            if (appBridge.isWenlaiActive && !appBridge.sliceMode) {
                appBridge.loadNextWenlaiSegment();
            } else {
                appBridge.loadNextSlice();
            }
        }
    }

    function handleKeyPressEvent(event) {
        var shortcutPressed = (event.modifiers & Qt.ControlModifier) || (event.modifiers & Qt.MetaModifier);

        // --- Enter 暂停 / 继续 ---
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (appBridge)
                appBridge.toggleTypingPause();
            event.accepted = true;
            return;
        }

        // 检测是否按下了平台快捷键修饰键（Windows/Linux: Ctrl, macOS: Command）
        if (shortcutPressed) {
            if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) {
                // 放大
                fontMetricsText.sharedFontSize = Math.min(72, fontMetricsText.sharedFontSize + 2);
                event.accepted = true;
            } else if (event.key === Qt.Key_Minus) {
                // 缩小
                fontMetricsText.sharedFontSize = Math.max(8, fontMetricsText.sharedFontSize - 2);
                event.accepted = true;
            }
        }

        // --- F2 按键响应（载文设置）---
        if (event.key === Qt.Key_F2) {
            typingPage.openSliceConfig();
            event.accepted = true;
        }

        // --- F3 按键响应 ---
        if (event.key === Qt.Key_F3) {
            handleRetypeRequest();
            event.accepted = true;
        }

        // --- F4 按键响应 ---
        if (event.key === Qt.Key_F4) {
            if (appBridge)
                appBridge.requestShuffle();
            event.accepted = true;
        }

        // --- Ctrl+L 乱序 ---
        if (shortcutPressed && event.key === Qt.Key_L) {
            if (appBridge)
                appBridge.requestShuffle();
            event.accepted = true;
        }

        // --- Ctrl+R 晴发文 ---
        if (shortcutPressed && event.key === Qt.Key_R) {
            triggerRandomWenlaiText();
            event.accepted = true;
        }

        // --- Ctrl+O 上一段（Ctrl+U 保留为兼容别名）---
        if (shortcutPressed && (event.key === Qt.Key_O || event.key === Qt.Key_U)) {
            triggerPrevSegment();
            event.accepted = true;
        }

        // --- Ctrl+P 下一段 ---
        if (shortcutPressed && event.key === Qt.Key_P) {
            triggerNextSegment();
            event.accepted = true;
        }

        // --- Ctrl+V 剪贴板载文 ---
        if (shortcutPressed && event.key === Qt.Key_V) {
            if (appBridge)
                appBridge.loadTextFromClipboard();
            event.accepted = true;
        }

        // --- Ctrl+D 发文 ---
        if (shortcutPressed && event.key === Qt.Key_D) {
            toolLine.requestSendText();
            event.accepted = true;
        }
    }

    //======================================

    // 监听键盘按键
    focus: true

    Shortcut {
        sequence: "Ctrl+R"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerRandomWenlaiText()
    }

    Shortcut {
        sequence: "Meta+R"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerRandomWenlaiText()
    }

    Shortcut {
        sequence: "Ctrl+O"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerPrevSegment()
    }

    Shortcut {
        sequence: "Meta+O"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerPrevSegment()
    }

    Shortcut {
        sequence: "Ctrl+D"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: toolLine.requestSendText()
    }

    Shortcut {
        sequence: "Ctrl+U"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerPrevSegment()
    }

    Shortcut {
        sequence: "Meta+U"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerPrevSegment()
    }

    Shortcut {
        sequence: "Ctrl+P"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerNextSegment()
    }

    Shortcut {
        sequence: "Meta+P"
        context: Qt.WindowShortcut
        enabled: typingPage.active
        onActivated: typingPage.triggerNextSegment()
    }

    // ==========================================
    // 字体加载与配置（阅读/跟打专用）
    // ==========================================

    // 内置默认字体（fallback）
    FontLoader {
        id: defaultFontLoader
        source: resourceBaseUrl + "fonts/LXGWWenKai-Regular.ttf"
    }

    // 用户自选字体：初始用属性绑定加载，后续用信号更新
    FontLoader {
        id: userFontLoader
        source: {
            if (!appBridge || !appBridge.readerFontPath) return "";
            return "file://" + appBridge.readerFontPath;
        }
    }

    // 阅读区字体配置
    FontMetrics {
        id: fontMetricsText
        property int sharedFontSize: 40
        font.family: {
            if (userFontLoader.status === FontLoader.Ready)
                return userFontLoader.name;
            if (defaultFontLoader.status === FontLoader.Ready)
                return defaultFontLoader.name;
            return "monospace";
        }
        font.pointSize: fontMetricsText.sharedFontSize
    }

    // 载文结果必须始终处理，不守卫 active——否则异步载文完成时若页面恰好非活跃
    // （如窗口管理器短暂失焦），textLoaded 信号被静默丢弃，readOnly 卡在 true。
    Connections {
        target: appBridge

        function onTextLoaded(text, textId, sourceLabel) {
            applyLoadedText(text);
            typingPage.refreshZitiHint();
            if (appBridge && textId > 0) {
                appBridge.setTextId(textId);
            }
            if (appBridge && sourceLabel) {
                appBridge.setTextTitle(sourceLabel);
            }
        }

        function onTextLoadFailed(message) {
            // 加载失败时只更新显示文本，不调用 handleLoadedText（不禁用 readOnly）
            // 用户无法在加载失败的文本上打字
            upperPane.text = message;
        }

        function onWenlaiLoadFailed(message) {
            upperPane.text = message;
        }

        function onAiTextPartial(text) {
            upperPane.text = text;
        }

        function onAiTextFailed(message) {
            upperPane.text = message;
        }

        function onLocalArticleSegmentLoadFailed(message) {
            upperPane.text = message;
        }
    }

    // 光标/字体状态变化需要守卫，防止页面切换后旧事件干扰
    Connections {
        target: appBridge
        enabled: typingPage.active

        function onCursorPosChanged(newPos) {
            typingPage.refreshZitiHint();
        }

        function onZitiStateChanged() {
            typingPage.refreshZitiHint();
        }
    }

    // typingEnded/historyRecordUpdated 来自后台定时器，需要守卫防止旧实例重复弹窗
    Connections {
        target: appBridge
        enabled: typingPage.active

        function onHistoryRecordUpdated(newRecord) {
            // 确保 segmentNo 键始终存在，避免 TableModel role 警告
            if (newRecord.segmentNo === undefined) {
                newRecord.segmentNo = "";
            }
            historyArea.tableModel.insertRow(0, newRecord);
            while (historyArea.tableModel.rows.length > typingPage.historyMaxRows) {
                historyArea.tableModel.removeRow(historyArea.tableModel.rows.length - 1);
            }
        }

        function onTypingEnded() {
            if (appBridge && appBridge.sliceMode) {
                appBridge.collectSliceResult();
                var result = appBridge.checkSliceResult();
                if (result === "fail") {
                    // 基础指标未达标：降击 + 重打
                    lowerPane.suppressTextChanged = true;
                    lowerPane.text = "";
                    lowerPane.suppressTextChanged = false;
                    upperPane.setCursorAndScroll(0, false);
                    upperPane.text = "";
                    appBridge.handleSliceRetype();
                } else if (result === "pass") {
                    // 基础指标达标，但连达标次数未满：重打，不降击
                    lowerPane.suppressTextChanged = true;
                    lowerPane.text = "";
                    lowerPane.suppressTextChanged = false;
                    upperPane.setCursorAndScroll(0, false);
                    upperPane.text = "";
                    appBridge.handleSliceRetypeNoDecrease();
                } else {
                    // advance：连达标次数已满，推进下一段
                    if (appBridge.getOnFailAction() !== "none") {
                        lowerPane.suppressTextChanged = true;
                        lowerPane.text = "";
                        lowerPane.suppressTextChanged = false;
                        upperPane.setCursorAndScroll(0, false);
                        upperPane.text = "";
                        appBridge.loadNextSlice();
                    } else {
                        lowerPane.suppressTextChanged = true;
                        lowerPane.text = "";
                        lowerPane.suppressTextChanged = false;
                        appBridge.handleLoadedText(upperPane.textDocument, upperPane.text);
                        Qt.callLater(function() {
                            lowerPane.lastText = lowerPane.text;
                        });
                    }
                }
            } else if (appBridge && appBridge.isWenlaiActive && appBridge.wenlaiSegmentMode === "auto") {
                appBridge.loadNextWenlaiSegmentWithScore();
            } else {
                // 正常模式：复制成绩，不弹结束窗
                appBridge.copyScoreMessage();
            }
        }
    }

    // 同步 LowerPane 焦点状态到 Bridge
    Connections {
        target: lowerPane
        enabled: typingPage.active

        function onLowerPaneFocusChanged(hasFocus) {
            appBridge.setLowerPaneFocused(hasFocus);
        }
    }

    Connections {
        target: toolLine
        enabled: typingPage.active

        function onRequestShuffle() {
            appBridge.requestShuffle();
        }

        function onRequestLoadTextFromClipboard() {
            // 剪贴板载文，不提交成绩（text_id 为 None）
            appBridge.loadTextFromClipboard();
        }

        function onRequestLoadWenlai() {
            typingPage.triggerRandomWenlaiText();
        }

        function onRequestRetype() {
            handleRetypeRequest();
        }

        function onRequestToggleLeaderboard() {
            showLeaderboard = !showLeaderboard;
        }

        function onRequestOpenSliceConfig() {
            typingPage.openSliceConfig();
        }

        function onRequestSendText() {
            if (!appBridge || !upperPane) return;
            var text = upperPane.text;
            if (!text || text.length === 0) return;

            // 构建发文格式：参考 TypeSunny 的 sender_content
            // ponytail: 分片模式下标题末尾有 " X/Y" 后缀（载文 1/50），
            // 方括号里已有 [段 X/Y]，去掉标题中的避免重复
            var title = appBridge.textTitle || qsTr("未命名文本");
            if (appBridge.sliceMode || appBridge.isWenlaiActive) {
                title = title.replace(/ \d+\/\d+(?:（乱序）)?$/, '');
            }
            var charCount = text.length;
            var metaParts = [];

            // 段号信息：分片模式取实际段号，否则默认 1/1（QQ 机器人解析需要）
            // 确定段号：分片→sliceIndex，晴发文→wenlaiSegmentLabel，有 textId→用它，否则 1
            var seg = 1;
            var segTotal = 0;
            if (appBridge.sliceMode && appBridge.totalSliceCount > 0) {
                seg = appBridge.sliceIndex;
                segTotal = appBridge.totalSliceCount;
            } else if (appBridge.isWenlaiActive && appBridge.wenlaiSegmentLabel) {
                var wenlaiParts = appBridge.wenlaiSegmentLabel.split("/");
                seg = parseInt(wenlaiParts[0]) || 1;
                segTotal = parseInt(wenlaiParts[1]) || 0;
            } else if (appBridge.textId && appBridge.textId > 0) {
                seg = appBridge.textId;
            }
            // 段号信息
            if (segTotal > 0) {
                metaParts.push(qsTr("段 %1/%2").arg(seg).arg(segTotal));
            } else {
                metaParts.push(qsTr("段 %1").arg(seg));
            }
            metaParts.push(qsTr("%1字").arg(charCount));

            var firstLine = title + " [" + metaParts.join(" ") + "]";
            var footer = "-----第" + seg + "段-TypeType";
            var output = firstLine + "\n" + text + "\n" + footer;
            appBridge.copyToClipboard(output);
        }
    }

    // 监听 sliceStatusChanged 更新状态栏 & 上传结果
    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onSliceStatusChanged(status) {
            typingPage.sliceStatusText = status;
        }

        function onSliceModeChanged() {
            typingPage.syncSliceStatus();
            typingPage.syncSliceCriteria();
        }

        function onUploadResult(success, message, textId) {
            if (success && textId > 0) {
                appBridge.setTextId(textId);
            }
        }
    }

    Keys.onPressed: function (event) {
        handleKeyPressEvent(event);
    }

    property bool firstActivation: true

    onActiveChanged: {
        if (active) {
            typingPage.syncSliceStatus();
            typingPage.syncSliceCriteria();
            if (appBridge && !appBridge.sliceMode && firstActivation) {
                firstActivation = false;
                appBridge.setTextTitle(appBridge.defaultTextTitle);
                appBridge.setTextId(0);
                // 同步调用（不用 Qt.callLater）：让 prepare_for_text_load() 立即设置
                // readOnly=true，使下方恢复代码在同一次 onActiveChanged 中就能看到
                // 正确的 textReadOnly 状态。requestLoadText 内部仅做计划+启动后台
                // Worker，不阻塞 UI。
                appBridge.requestLoadText(appBridge.defaultTextSourceKey);
            }
            // 恢复：载文期间/之后 readOnly 可能仍为 true（信号丢失、用户切走再回来等）。
            if (appBridge && appBridge.textReadOnly) {
                if (upperPane.text.length > 0) {
                    handleRetypeRequest();
                } else {
                    appBridge.requestLoadText(appBridge.defaultTextSourceKey);
                }
            }
        }
    }

    ColumnLayout {
        id: columnLayout
        anchors.fill: parent
        spacing: 0

        ToolLine {
            id: toolLine
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            Layout.minimumHeight: 56
            Layout.maximumHeight: 56
            wenlaiLoading: appBridge ? appBridge.wenlaiLoading : false
            aiTextLoading: appBridge ? appBridge.aiTextLoading : false
            onRequestAiText: {
                if (appBridge)
                    appBridge.requestAiText();
            }
        }

        TypingProgressBar {
            id: typingProgressBar
            Layout.fillWidth: true
            Layout.topMargin: 2
            Layout.bottomMargin: 2
            progress: appBridge ? appBridge.typingProgress : 0.0
            visible: appBridge && appBridge.charNum !== "0/0"
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            // 左侧主要内容区
            Flickable {
                id: leftFlickable
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: showLeaderboard ? parent.width - 300 - 8 : parent.width
                contentHeight: Math.max(leftColumn.implicitHeight, leftFlickable.height)
                clip: true

                ColumnLayout {
                    id: leftColumn
                    width: leftFlickable.width
                    height: Math.max(implicitHeight, leftFlickable.height)
                    spacing: 0

                    UpperPane {
                        id: upperPane
                        fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
                        fontFamily: fontMetricsText.font.family
                        Layout.fillWidth: true
                        Layout.preferredHeight: fontMetricsText.height * 4
                        Layout.minimumHeight: fontMetricsText.height > 0 ? fontMetricsText.height * 2 : 80
                    }

                    ScoreArea {
                        id: scoreArea
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        Layout.minimumHeight: 36
                        Layout.maximumHeight: 36
                    }

                    Rectangle {
                        id: zitiHintBar
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        Layout.minimumHeight: 30
                        Layout.maximumHeight: 30
                        visible: appBridge && appBridge.zitiEnabled && zitiHintText.text.length > 0
                        radius: 4
                        color: Theme.currentTheme
                            ? Theme.currentTheme.colors.cardColor
                            : "#f8f8f8"
                        border.color: Theme.currentTheme
                            ? Theme.currentTheme.colors.dividerBorderColor
                            : "#d8d8d8"
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 8

                            Text {
                                text: appBridge ? appBridge.zitiCurrentScheme : ""
                                font.pixelSize: 11
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.textSecondaryColor
                                    : "#666"
                            }

                            Text {
                                id: zitiHintText
                                Layout.fillWidth: true
                                text: typingPage.currentZitiHint
                                elide: Text.ElideRight
                                font.pixelSize: 13
                                font.bold: true
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.textColor
                                    : "#222"
                            }
                        }
                    }

                    LowerPane {
                        id: lowerPane
                        fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
                        fontFamily: fontMetricsText.font.family
                        Layout.fillWidth: true
                        // 固定高度：2倍字体高
                        Layout.preferredHeight: fontMetricsText.height > 0 ? fontMetricsText.height * 3 : 80
                        Layout.minimumHeight: fontMetricsText.height > 0 ? fontMetricsText.height * 2 : 80 // 保证最少能显示2行
                    }

                    Rectangle {
                        id: sliceStatusBar
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        Layout.bottomMargin: 8
                        Layout.preferredHeight: 40
                        Layout.minimumHeight: 40
                        visible: appBridge && appBridge.sliceMode

                        radius: 8
                        color: Theme.currentTheme
                            ? Theme.currentTheme.colors.cardColor
                            : "#f8f8f8"
                        border.color: Theme.currentTheme
                            ? Theme.currentTheme.colors.primaryColor
                            : "#4b88ff"
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 10

                            Rectangle {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                radius: 11
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.primaryColor + "20"
                                    : "#4b88ff20"

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("段")
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.primaryColor
                                        : "#4b88ff"
                                }
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    text: typingPage.sliceStatusPrimaryText()
                                    font.pixelSize: 13
                                    font.bold: true
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.textColor
                                        : "#222"
                                }

                                Text {
                                    text: typingPage.sliceStatusSecondaryText().length > 0
                                        ? typingPage.sliceStatusSecondaryText()
                                        : "分段模式下的成绩仅本地记录，不提交排行榜"
                                    font.pixelSize: 11
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.textSecondaryColor
                                        : "#666"
                                }
                            }

                            Text {
                                text: typingPage.sliceCriteriaText
                                font.pixelSize: 11
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.textSecondaryColor
                                    : "#666"
                                visible: typingPage.sliceCriteriaText.length > 0
                            }

                            Text {
                                text: appBridge ? "达标次数: " + appBridge.slicePassCount : ""
                                font.pixelSize: 12
                                font.bold: true
                                color: Theme.currentTheme
                                    ? Theme.currentTheme.colors.primaryColor
                                    : "#4b88ff"
                                visible: appBridge && appBridge.sliceMode
                            }

                            Item { Layout.fillWidth: true }

                            Button {
                                text: "\u2190 " + qsTr("上一段")
                                enabled: appBridge && appBridge.sliceIndex > 1
                                visible: enabled
                                onClicked: {
                                    if (appBridge) {
                                        appBridge.loadPrevSlice();
                                    }
                                }
                            }

                            Button {
                                text: qsTr("随机段")
                                enabled: appBridge && appBridge.sliceMode
                                onClicked: {
                                    if (appBridge) {
                                        appBridge.loadRandomSlice();
                                    }
                                }
                            }

                            Button {
                                text: qsTr("下一段") + " \u2192"
                                enabled: appBridge && appBridge.sliceIndex < appBridge.totalSliceCount
                                visible: enabled
                                onClicked: {
                                    if (appBridge) {
                                        appBridge.loadNextSlice();
                                    }
                                }
                            }
                        }
                    }

                    HistoryArea {
                        id: historyArea
                        Layout.fillWidth: true
                        Layout.fillHeight: true  // 拿走所有剩余空间
                        Layout.minimumHeight: 72  // 最小高度保证至少能看到一条历史记录
                    }
                }
            }

            // 右侧排行榜面板
            LeaderboardPanel {
                id: leaderboardPanel
                Layout.preferredWidth: showLeaderboard ? 300 : 0
                Layout.fillHeight: true
                Layout.minimumHeight: 200
                visible: showLeaderboard
                textId: appBridge ? appBridge.textId : 0
                onCloseRequested: showLeaderboard = false

                Behavior on Layout.preferredWidth {
                    NumberAnimation {
                        duration: 200
                        easing.type: Easing.OutQuad
                    }
                }
            }
        }

        Rectangle {
            id: typingTotalsBar
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            Layout.minimumHeight: 30
            Layout.maximumHeight: 30
            color: Theme.currentTheme
                ? Theme.currentTheme.colors.cardColor
                : "#f8f8f8"
            border.color: Theme.currentTheme
                ? Theme.currentTheme.colors.dividerBorderColor
                : "#e0e0e0"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                Text {
                    Layout.fillWidth: true
                    text: appBridge ? appBridge.windowTitle : "TypeType"
                    elide: Text.ElideRight
                    font.pixelSize: 12
                    color: Theme.currentTheme
                        ? Theme.currentTheme.colors.textSecondaryColor
                        : "#666"
                }

                Text {
                    text: appBridge
                        ? qsTr("今日字数: ") + appBridge.todayTypedChars + qsTr("  总字数: ") + appBridge.totalTypedChars
                        : ""
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.currentTheme
                        ? Theme.currentTheme.colors.textColor
                        : "#222"
                }
            }
        }
    }

    EndDialog {
        id: endDialog
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        property bool isSliceAggregate: false
    }

}
