import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../typing"
import "../components"

Item {
    id: typingPage
    property bool loggedin: false  // Will be injected by NavigationView
    property bool showLeaderboard: false

    //=====================================
    // 函数
    //=====================================

    function handleRetypeRequest() {
        lowerPane.text = "";
        if (appBridge)
            appBridge.handleStartStatus(false);
    }

    function applyLoadedText(plainText) {
        // 先改lowerPaneText，再改upperPaneText (用于正确计算wrongNum)
        lowerPane.text = "";
        upperPane.text = plainText;
        appBridge.handleLoadedText(upperPane.textDocument);
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
        enabled: typingPage.StackView.status === StackView.Active

        function onTextLoaded(text, textId, sourceLabel) {
            // 载文 Dialog 打开时，textLoaded 供 Dialog 预览，不应用到打字区
            if (typingPage.sliceDialogOpen) {
                return;
            }
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
        enabled: typingPage.StackView.status === StackView.Active

        function onHistoryRecordUpdated(newRecord) {
            // 载文模式：在字数列追加片索引标记
            if (newRecord.slice_index !== undefined && newRecord.slice_index > 0) {
                var total = appBridge ? appBridge.totalSliceCount : 0;
                newRecord.charNum = String(newRecord.charNum) + " [" + newRecord.slice_index + "/" + total + "]";
            }
            historyArea.tableModel.insertRow(0, newRecord);
        }

        function onTypingEnded() {
            if (appBridge && appBridge.sliceMode) {
                // 载文模式：跳过 EndDialog，自动推进
                appBridge.collectSliceResult();
                if (appBridge.isLastSlice()) {
                    // 最后一片：弹出综合成绩
                    var msg = appBridge.buildAggregateScore();
                    endDialog.scoreMessage = msg;
                    endDialog.isSliceAggregate = true;
                    endDialog.open();
                    appBridge.exitSliceMode();
                } else {
                    // 判断重打条件
                    if (appBridge.shouldRetype()) {
                        appBridge.handleSliceRetype();
                    } else {
                        appBridge.loadNextSlice();
                    }
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
        enabled: typingPage.StackView.status === StackView.Active

        function onLowerPaneFocusChanged(hasFocus) {
            appBridge.setLowerPaneFocused(hasFocus);
        }
    }

    Connections {
        target: toolLine
        enabled: typingPage.StackView.status === StackView.Active

        function onRequestShuffle() {
            appBridge.requestShuffle();
        }

        function onRequestLoadText(sourceKey) {
            appBridge.requestLoadText(sourceKey);
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

    // 监听上传结果：云端上传成功时自动设置 text_id
    Connections {
        target: appBridge
        enabled: appBridge !== null
        function onUploadResult(success, message, textId) {
            if (success && textId > 0) {
                appBridge.setTextId(textId);
            }
        }
    }

    Keys.onPressed: function (event) {
        handleKeyPressEvent(event);
    }

    StackView.onActivating: {
        if (appBridge) {
            appBridge.setTextTitle(appBridge.defaultTextTitle);
            appBridge.setTextId(0);
        }
    }

    StackView.onActivated: {
        if (appBridge) {
            Qt.callLater(function () {
                appBridge.requestLoadText(appBridge.defaultTextSourceKey);
            });
        }
    }

    ColumnLayout {
        id: columnLayout
        anchors.fill: parent
        spacing: 0

        ToolLine {
            id: toolLine
            textSourceOptions: appBridge ? appBridge.textSourceOptions : []
            defaultTextSourceKey: appBridge ? appBridge.defaultTextSourceKey : ""
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

    // 载文 Dialog 打开时，阻止 textLoaded 应用到打字区（仅供 Dialog 预览）
    property bool sliceDialogOpen: sliceConfigDialog.visible

    // 载文模式状态栏
    Rectangle {
        id: sliceStatusBar
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 28
        visible: appBridge && appBridge.sliceMode

        color: Theme.currentTheme
            ? Theme.currentTheme.colors.systemCautionColor + "18"
            : "#fff3cd"
        border.color: Theme.currentTheme
            ? Theme.currentTheme.colors.systemCautionColor + "40"
            : "#ffc10740"
        border.width: 1

        Text {
            anchors.centerIn: parent
            text: {
                if (!appBridge || !appBridge.sliceMode) return "";
                return appBridge.getSliceStatus();
            }
            font.pixelSize: 12
            color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
        }
    }

    // 监听 sliceStatusChanged 更新状态栏
    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onSliceStatusChanged(status) {
            // 状态栏文本通过 getSliceStatus() 自动更新
        }
    }
}
