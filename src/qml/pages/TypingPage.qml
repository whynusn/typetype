import QtQuick 2.15
import QtQuick.Controls 2.15
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

    function sliceStatusPrimaryText() {
        var parts = typingPage.sliceStatusText.split("  |  ");
        return parts.length > 0 ? parts[0] : "";
    }

    function sliceStatusSecondaryText() {
        var parts = typingPage.sliceStatusText.split("  |  ");
        return parts.length > 1 ? parts[1] : "";
    }

    function handleKeyPressEvent(event) {
        // 检测是否按下了 Ctrl 键
        if (event.modifiers & Qt.ControlModifier) {
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
    }

    //======================================

    // 监听键盘按键
    focus: true

    // ==========================================
    // 字体加载与配置（阅读/跟打专用）
    // ==========================================

    // 加载 阅读/跟打 字体（UI 字体由 main.py 中 app.setFont() 全局设定）
    FontLoader {
        id: readerFontLoader
        source: resourceBaseUrl + "fonts/LXGWWenKai-Regular-subset.ttf"
    }

    // 阅读区字体配置
    FontMetrics {
        id: fontMetricsText
        property int sharedFontSize: 40
        // 逻辑：优先使用加载的 LXGW，如果没加载出来，回退到系统衬线/等宽字体
        font.family: readerFontLoader.status === FontLoader.Ready ? readerFontLoader.name : "monospace"
        font.pointSize: fontMetricsText.sharedFontSize
    }

    // textLoaded/textLoadFailed 只在 requestLoadText() 主动调用后才发出，需要守卫防止页面切换后旧请求完成阻塞
    Connections {
        target: appBridge
        enabled: typingPage.active

        function onTextLoaded(text, textId, sourceLabel) {
            applyLoadedText(text);
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
    }

    // typingEnded/historyRecordUpdated 来自后台定时器，需要守卫防止旧实例重复弹窗
    Connections {
        target: appBridge
        enabled: typingPage.active

        function onHistoryRecordUpdated(newRecord) {
            // 载文模式：在字数列追加片索引标记（通过 sliceInfo 传递，避免修改 charNum 类型）
            if (newRecord.slice_index !== undefined && newRecord.slice_index > 0) {
                var total = appBridge ? appBridge.totalSliceCount : 0;
                newRecord.sliceInfo = String(newRecord.charNum) + " [" + newRecord.slice_index + "/" + total + "]";
            }
            historyArea.tableModel.insertRow(0, newRecord);
        }

        function onTypingEnded() {
            if (appBridge && appBridge.sliceMode) {
                // 载文模式：跳过 EndDialog，自动推进
                appBridge.collectSliceResult();
                if (appBridge.shouldRetype()) {
                    appBridge.handleSliceRetype();
                } else if (appBridge.isLastSlice()) {
                    // 最后一片：弹出综合成绩
                    var msg = appBridge.buildAggregateScore();
                    endDialog.scoreMessage = msg;
                    endDialog.isSliceAggregate = true;
                    endDialog.open();
                    appBridge.exitSliceMode();
                } else {
                    appBridge.loadNextSlice();
                }
            } else {
                // 正常模式
                endDialog.scoreMessage = appBridge.getScoreMessage();
                endDialog.isSliceAggregate = false;
                endDialog.open();
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

        function onRequestRetype() {
            handleRetypeRequest();
        }

        function onRequestToggleLeaderboard() {
            showLeaderboard = !showLeaderboard;
        }

        function onRequestOpenSliceConfig() {
            sliceConfigDialog.open();
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
            if (appBridge && !appBridge.sliceMode && firstActivation) {
                firstActivation = false;
                appBridge.setTextTitle(appBridge.defaultTextTitle);
                appBridge.setTextId(0);
                Qt.callLater(function () {
                    appBridge.requestLoadText(appBridge.defaultTextSourceKey);
                });
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
                                    text: "片"
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
                                        : "分片模式下的成绩仅本地记录，不提交排行榜"
                                    font.pixelSize: 11
                                    color: Theme.currentTheme
                                        ? Theme.currentTheme.colors.textSecondaryColor
                                        : "#666"
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
    }

    EndDialog {
        id: endDialog
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        property bool isSliceAggregate: false
    }

    SliceConfigDialog {
        id: sliceConfigDialog
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        textSourceOptions: appBridge ? appBridge.textSourceOptions : []
        defaultTextSourceKey: appBridge ? appBridge.defaultTextSourceKey : ""
    }

}
