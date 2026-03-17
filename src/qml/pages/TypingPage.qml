import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../typing"
import "../components"

Item {
    id: typingPage

    //=====================================
    // 函数
    //=====================================

    function handleRetypeRequest() {
        lowerPane.text = "";
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
        source: resourceBaseUrl + "fonts/LXGWWenKai-Regular.ttf"
    }

    // 阅读区字体配置
    FontMetrics {
        id: fontMetricsText
        property int sharedFontSize: 40
        // 逻辑：优先使用加载的 LXGW，如果没加载出来，回退到系统衬线/等宽字体
        font.family: readerFontLoader.status === FontLoader.Ready ? readerFontLoader.name : "monospace"
        font.pointSize: fontMetricsText.sharedFontSize
    }

    // StackView 每次导航都会 createObject 创建新页面实例，旧实例不会被销毁。
    // 因此所有 Connections 必须加 enabled 守卫，只在页面处于栈顶时才响应信号，
    // 否则多个实例同时响应同一信号会导致重复弹窗等问题。

    // 页面离开时停止打字并重置状态（打字是连续过程，切走 = 中断）
    StackView.onDeactivating: {
        appBridge.requestLoadText("builtin_demo");
    }

    Connections {
        target: appBridge
        enabled: typingPage.StackView.status === StackView.Active

        function onHistoryRecordUpdated(newRecord) {
            historyArea.tableModel.insertRow(0, newRecord);
        }

        function onTypingEnded() {
            if (qmlDebug)
                console.log("Typing ended");
            endDialog.scoreMessage = appBridge.getScoreMessage();
            endDialog.open();
        }

        function onTextLoaded(text) {
            applyLoadedText(text);
        }

        function onTextLoadFailed(message) {
            applyLoadedText(message);
        }
    }

    // 用 Connections 把 backend 的信号连接到 appBridge 的方法
    Connections {
        target: backend  // Python 暴露的 Backend 单例
        enabled: typingPage.StackView.status === StackView.Active

        function onKeyPressed(keyCode, deviceName) {
            if (lowerPane.isFocus) {
                if (appBridge.isStart()) {
                    appBridge.handlePressed();
                }
            }
        }
    }

    Connections {
        target: toolLine
        enabled: typingPage.StackView.status === StackView.Active

        function onRequestLoadText(sourceKey) {
            appBridge.requestLoadText(sourceKey);
        }

        function onRequestLoadTextFromClipboard() {
            appBridge.loadTextFromClipboard();
        }

        function onRequestRetype() {
            handleRetypeRequest();
        }
    }

    Keys.onPressed: function (event) {
        handleKeyPressEvent(event);
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
            Layout.preferredHeight: 72
            Layout.minimumHeight: 72
            Layout.maximumHeight: 72
        }

        UpperPane {
            id: upperPane
            fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
            fontFamily: fontMetricsText.font.family
            Layout.fillHeight: true
            Layout.fillWidth: true
            Layout.minimumHeight: fontMetricsText.height * 2  // 最小高度：2倍字体高
        }

        ScoreArea {
            id: scoreArea
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.minimumHeight: 40
            Layout.maximumHeight: 40
        }

        LowerPane {
            id: lowerPane
            fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
            fontFamily: fontMetricsText.font.family
            Layout.fillWidth: true
            // 固定高度：2倍字体高
            Layout.preferredHeight: fontMetricsText.height * 2
            Layout.minimumHeight: fontMetricsText.height * 2 // 保证最少能显示2行
        }

        HistoryArea {
            id: historyArea
            Layout.fillWidth: true
            Layout.preferredHeight: 144
            Layout.minimumHeight: 72
        }
    }

    EndDialog {
        id: endDialog
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
    }
}
