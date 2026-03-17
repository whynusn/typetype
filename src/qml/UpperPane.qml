// qml/UpperPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI as Rin

Pane {
    id: root

    property alias textDocument: textArea.textDocument
    property alias text: textArea.text
    property alias fontSize: textArea.font.pixelSize  // 暴露字体大小属性
    property alias fontFamily: textArea.font.family

    background: Rectangle {
        color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.cardColor : "#f5f5f5"
        border.color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        border.width: 1
        radius: 2
    }

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
            color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.textColor : "black"
            background: Rectangle { color: "transparent" }

            // 把底层的 textDocument（QQuickTextDocument）传给 Python 的 appBridge
            Component.onCompleted: {
                // 载入初始文本
                if (appBridge) {
                    appBridge.handleLoadedText(textArea.textDocument);
                }
            }

            function setCursorAndScroll(cursorPos) {
                textArea.cursorPosition = cursorPos;

                // 获取光标所在行的矩形信息
                var rect = textArea.positionToRectangle(cursorPos);
                if (!rect) return;

                // 目标：光标所在行顶部 - 1 行边距，位于视口顶部
                var targetY = Math.max(rect.y - rect.height, 0);

                // 设置滚动位置（通过 ScrollView 的 contentItem）
                scrollView.contentItem.contentY = targetY;
            }

            onTextChanged: {
                if (appBridge) {
                    setCursorAndScroll(appBridge.getCursorPos());
                }
            }
        }
    }
}
