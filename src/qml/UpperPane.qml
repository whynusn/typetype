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
                // 计算总行数
                var totalLines = textArea.lineCount;

                // 获取光标位置的矩形
                var rect = textArea.positionToRectangle(cursorPos);
                if (!rect) {
                    return;
                }

                // 计算行高
                var lineHeight = textArea.contentHeight / totalLines;

                // 计算文本底部高度(注意 `textArea` 与 `scrollView` 之间有间隙, 通过取余拿到)
                var sep = rect.y % lineHeight;
                var textBottomHeight = sep * 2 + textArea.contentHeight;

                // 计算光标所在行的起始位置
                var currentLineY = rect.y;
                var targetLineY = currentLineY + lineHeight;

                // 底部提前可见行数
                var bottomVisibleLines = 1;

                // 如果是最后 `bottomVisibleLines` 行，直接看到底部即可
                var targetY = Math.min(targetLineY + bottomVisibleLines * lineHeight + sep, textBottomHeight);

                // 计算滚动位置：视口左上角的Y坐标
                var scrollY = targetY - scrollView.contentItem.height;

                // 确保滚动位置在有效范围内
                scrollY = Math.max(0, scrollY);

                // 设置滚动位置（通过 ScrollView 的 contentItem）
                scrollView.contentItem.contentY = scrollY;

            // 光标位置设置为滚动后的当前位置
            //textArea.cursorPosition = cursorPos;
            }

            onTextChanged: {
                if (bridge) {
                    setCursorAndScroll(bridge.getCursorPos());
                }
            }
        }
    }
}
