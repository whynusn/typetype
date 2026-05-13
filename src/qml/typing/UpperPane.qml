// qml/UpperPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import RinUI as Rin

QQC.Pane {
    id: root

    property alias textDocument: textArea.textDocument
    property alias text: textArea.text
    property alias fontSize: textArea.font.pixelSize  // 暴露字体大小属性
    property alias fontFamily: textArea.font.family

    function setCursorAndScroll(cursorPos, forceScroll) {
        textArea.setCursorAndScroll(cursorPos, forceScroll);
    }

    // 监听 appBridge 的光标位置变化，同步 UpperPane
    Connections {
        target: appBridge
        function onCursorPosChanged(newPos) {
            textArea.setCursorAndScroll(newPos);
        }
    }

    background: Rectangle {
        color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.cardColor : "#f5f5f5"
        border.color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.dividerBorderColor : "#e0e0e0"
        border.width: 1
        radius: 2
    }

    QQC.ScrollView {
        id: scrollView
        anchors.fill: parent
        clip: true // 确保文字不超出 Pane 的边界

        // 在 Qt 6 中，ScrollBar 应该附加给 ScrollView
        QQC.ScrollBar.vertical: QQC.ScrollBar {
            policy: QQC.ScrollBar.AsNeeded

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

        QQC.TextArea {
            id: textArea
            readOnly: true
            wrapMode: QQC.TextArea.Wrap
            textFormat: TextEdit.PlainText   // PlainText 避免 RichText 转换导致 toPlainText() 异常
            font.pixelSize: 14
            text: "你好，世界。"
            color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.textColor : "black"
            background: Rectangle {
                color: "transparent"
            }

            // 把底层的 textDocument（QQuickTextDocument）传给 Python 的 appBridge
            // 注意：不在这里调 handleLoadedText，等文本加载完成后再由 applyLoadedText 调用
            // 避免用户在 text_id 尚未设置时就开始打字

            function setCursorAndScroll(cursorPos, forceScroll) {
                if (cursorPos < 0 || cursorPos > textArea.length) {
                    return;
                }
                var targetPos = Math.min(cursorPos, Math.max(0, textArea.length - 1));
                textArea.cursorPosition = targetPos;

                Qt.callLater(function() {
                    textArea.scrollToPosition(targetPos, forceScroll === true);
                });
            }

            function scrollToPosition(cursorPos, forceScroll) {
                // 获取光标所在行的矩形信息
                var rect = textArea.positionToRectangle(cursorPos);
                if (!rect)
                    return;

                var currentY = scrollView.contentItem.contentY;
                var centerY = scrollView.height * 0.48;
                var targetY = Math.max(rect.y + rect.height / 2 - centerY, 0);
                var maxY = Math.max(0, textArea.contentHeight - scrollView.height);
                targetY = Math.min(targetY, maxY);

                var lineHeight = Math.max(rect.height, textArea.font.pixelSize);
                if (forceScroll === true || Math.abs(currentY - targetY) > lineHeight * 0.8) {
                    scrollView.contentItem.contentY = targetY;
                }
            }
        }
    }
}
