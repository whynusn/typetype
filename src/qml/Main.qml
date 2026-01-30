// qml/main.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

// 自定义模块
import src.backend.textproperties 1.0

ApplicationWindow {
    id: root
    visible: true
    width: 758
    height: 600
    title: "TypeType"

    // ==========================================
    // 1. 加载字体文件 (确保字体文件路径正确，推荐放在 qrc 资源文件中)
    // ==========================================

    // 加载 UI 字体
    FontLoader {
        id: uiFontLoader
        source: "qrc:/resources/fonts/HarmonyOS_Sans_SC_Regular.ttf" // 请确保路径对应你实际的文件位置
    }

    // 加载 阅读/跟打 字体
    FontLoader {
        id: readerFontLoader
        source: "qrc:/resources/fonts/LXGWWenKai-Regular.ttf"
    }

    // ==========================================
    // 2. 定义全局字体配置
    // ==========================================

    // UI 字体配置
    FontMetrics {
        id: fontMetricsUI
        property int sharedFontSize: 20
        // 逻辑：优先使用加载的 Inter 名称，如果没加载出来，回退到系统无衬线字体
        font.family: uiFontLoader.status === FontLoader.Ready ? uiFontLoader.name : "sans-serif"
        font.pointSize: fontMetricsUI.sharedFontSize
    }

    // 阅读区字体配置
    FontMetrics {
        id: fontMetricsText
        property int sharedFontSize: 40
        // 逻辑：优先使用加载的 LXGW，如果没加载出来，回退到系统衬线/等宽字体
        font.family: readerFontLoader.status === FontLoader.Ready ? readerFontLoader.name : "monospace"
        font.pointSize: fontMetricsText.sharedFontSize
    }

    // 实例化 Bridge
    Bridge {
        id: bridge
    }

    Connections {
        target: bridge

        function onHistoryRecordUpdated(newRecord) {
            //console.log("History record updated:", newRecord.date);
            historyArea.tableModel.appendRow(newRecord);
        }
    }

    // 用 Connections 把 backend 的信号连接到 bridge 的方法
    Connections {
        target: backend  // Python 暴露的 Backend 单例

        function onKeyPressed(keyCode, deviceName) {
            //console.log(lowerPane.isFocus);
            if (lowerPane.isFocus) {
                /** 开始逻辑在 `LowerPane` 中定义, 此处无需重复
                if (!bridge.isStart() && !bridge.isReadOnly() && isPrintable == "visable") {
                    bridge.handleStartStatus(true);
                }
                 */
                if (bridge.isStart()) {
                    bridge.handlePressed();
                }
                //console.log(bridge.isStart());
            }
        }
    }
    Connections {
        target: toolLine

        function onRequestLoadText() {
            var newText = bridge.handleLoadTextRequest();
            // 先改lowerPaneText，再改upperPaneText (用于正确计算wrongNum)
            lowerPane.text = "";
            upperPaneLoadText(newText);
        }

        function onRequestLoadTextFromClipboard() {
            var newText = bridge.handleLoadTextFromClipboardRequest();
            // 先改lowerPaneText，再改upperPaneText (用于正确计算wrongNum)
            lowerPane.text = "";
            upperPaneLoadText(newText);
        }

        function onRequestRetype() {
            handleRetypeRequest();
        }

        function upperPaneLoadText(plainText) {
            upperPane.text = plainText;
            bridge.handleLoadedText(upperPane.textDocument);
        }
    }

    //=====================================
    // 函数
    //=====================================

    function handleRetypeRequest() {
        lowerPane.text = "";
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

    Item {
        id: item
        // 监听键盘按键
        anchors.fill: parent
        focus: true  // 必须有焦点才能捕获按键
        Keys.onPressed: function (event) {
            handleKeyPressEvent(event);
        }
        ColumnLayout {
            id: columnLayout
            anchors.fill: parent
            spacing: 0

            ToolLine {
                id: toolLine
                fontSize: fontMetricsUI.sharedFontSize  // 绑定到共享属性
                fontFamily: fontMetricsUI.font.family
                bridge: bridge
                Layout.fillWidth: true
                Layout.preferredHeight: fontMetricsUI.height * 2
                Layout.minimumHeight: fontMetricsUI.height * 2
                Layout.maximumHeight: fontMetricsUI.height * 2
            }

            UpperPane {
                id: upperPane
                fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
                fontFamily: fontMetricsText.font.family
                bridge: bridge
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.minimumHeight: fontMetricsText.height * 2  // 最小高度：1倍字体高

            }

            ScoreArea {
                id: scoreArea
                fontSize: fontMetricsUI.sharedFontSize  // 绑定到共享属性
                fontFamily: fontMetricsUI.font.family
                bridge: bridge
                Layout.fillWidth: true
                Layout.preferredHeight: fontMetricsUI.height * 0.8
                Layout.minimumHeight: fontMetricsUI.height * 0.8
                Layout.maximumHeight: fontMetricsUI.height * 0.8
            }

            LowerPane {
                id: lowerPane
                fontSize: fontMetricsText.sharedFontSize  // 绑定到共享属性
                fontFamily: fontMetricsText.font.family
                bridge: bridge
                isSpecialPlatform: backend.isSpecialPlatform
                Layout.fillWidth: true
                // 固定高度：2倍字体高
                Layout.preferredHeight: fontMetricsText.height * 2
                Layout.minimumHeight: fontMetricsText.height * 2 // 保证最少能显示2行
            }

            HistoryArea {
                id: historyArea
                fontSize: fontMetricsUI.sharedFontSize  // 绑定到共享属性
                fontFamily: fontMetricsUI.font.family
                rowHeight: fontMetricsUI.height
                Layout.fillWidth: true
                Layout.preferredHeight: fontMetricsUI.height * 4
                Layout.minimumHeight: fontMetricsUI.height * 2 // 保证最少能显示2行
            }
        }
    }
}
