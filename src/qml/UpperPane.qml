// qml/UpperPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15

Pane {
    id: root

    property alias textDocument: textArea.textDocument
    property alias text: textArea.text
    property alias bridge: textArea.bridge
    property alias fontSize: textArea.font.pixelSize  // 暴露字体大小属性
    property alias fontFamily: textArea.font.family

    ScrollView {
        id: scrollView
        anchors.fill: parent
        clip: true // 确保文字不超出 Pane 的边界

        // 在 Qt 6 中，ScrollBar 应该附加给 ScrollView
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded

            // **位置控制**：通过 anchors 调整
            anchors.right: parent.right          // 贴在右侧
            anchors.rightMargin: 5              // 右边距 5px
            anchors.top: parent.top             // 顶部对齐
            anchors.topMargin: 10               // 顶部边距 10px
            anchors.bottom: parent.bottom       // 底部对齐
            anchors.bottomMargin: 10            // 底部边距 10px

            // **大小控制**
            width: 12                           // 滚动条宽度 12px
            // 高度会自动根据 anchors 计算
        }

        TextArea {
            id: textArea
            readOnly: true
            wrapMode: TextArea.Wrap
            textFormat: TextEdit.RichText   // 支持富文本格式
            font.pixelSize: 14
            text: "你好，世界。"

            property var bridge: null  // 将外部 Bridge 传进来使用（可选）

            // 把底层的 textDocument（QQuickTextDocument）传给 Python 的 bridge
            Component.onCompleted: {
                // 载入初始文本
                if (bridge) {
                    bridge.handleLoadedText(textArea.textDocument);
                }
            }

            function setCursorAndScroll(cursorPos) {
                textArea.cursorPosition = cursorPos + 6; // 魔法数字，为了提前将可视区域下移
            }

            onTextChanged: {
                if (bridge) {
                    setCursorAndScroll(bridge.getCursorPos());
                }
            }
        }
    }
}
