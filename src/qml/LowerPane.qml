// qml/LowerPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15

Pane {
    id: root
    property alias text: textArea.text
    property alias bridge: scrollView.bridge
    property alias fontSize: textArea.font.pixelSize
    property alias fontFamily: textArea.font.family
    property alias isFocus: textArea.activeFocus
    //property alias textReadOnly: textArea.readOnly

    // 记录上一次的文本长度，用于计算增量
    property string lastText: ""
    property bool isSpecialPlatform: false

    ScrollView {
        id: scrollView
        anchors.fill: parent
        clip: true // 确保文字不超出 Pane 的边界

        // 在 Qt 6 中，ScrollBar 应该附加给 ScrollView
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        property var bridge: null

        TextArea {
            id: textArea
            wrapMode: TextEdit.Wrap
            font.pixelSize: 14
            verticalAlignment: TextInput.AlignTop // 文字靠上
            width: scrollView.width // 宽度绑定到 scrollView，保证换行正确

            readOnly: scrollView.bridge.textReadOnly

            onCursorPositionChanged: {
                //console.log("cursorPosition =", cursorPosition);
                scrollView.bridge.setCursorPos(cursorPosition);
            }

            // ==========================================
            // 监听“正在输入的拼音/预编辑内容”
            // ==========================================
            onPreeditTextChanged: {
                // 这个参数就是输入法浮窗里显示的拼音（比如 "hao" 或 "hao ma"）
                //console.log("预编辑内容变化:", preeditText);
                if (preeditText === "") {
                    //console.log("这是空, 说明此时可能有上屏行为");
                }

                if (bridge) {
                    // 你可以把拼音传给后端，做一些实时反馈（比如高亮匹配项）
                    //bridge.handlePinyin(preeditText);

                    /*
                    if (preeditText==='' && text===''){
                        bridge.handleStartStatus(false);
                    } else {
                        bridge.handleStartStatus(true);
                    }
					*/

                }
            }

            // ==========================================
            // 捕获上屏字符
            // ==========================================
            onTextChanged: {
                // if (bridge) bridge.onInputEnd();

                // 这里是你之前的“提取增量字符”的逻辑
                var currentText = text;
                // 注意：这里需要处理“用户删字”的情况
                var startPos = textArea.cursorPosition;
                var growLength = currentText.length - root.lastText.length;
                if (growLength > 0)
                    startPos -= growLength;
                var committedText = currentText.substring(startPos);

                //console.log("textChanged!!\n");

                if (bridge) {
                    //==============================================
                    // 处理按键事件
                    //==============================================
                    if (preeditText === '' && currentText === '') {
                        console.log("Set false because no text");
                        bridge.handleStartStatus(false);
                    } else if (!bridge.isStart() && !bridge.isReadOnly()) {
                        console.log("Set true status by LowePane's textChanged event.");
                        bridge.handleStartStatus(true);
                        if (root.isSpecialPlatform) {
                            bridge.handlePressed(); // 第一下按键别忘了统计, 后续按键由全局监听器统计
                        }
                    }

                    //console.log("平台特殊性已暴露到qml中：" + root.isSpecialPlatform);
                    if (!root.isSpecialPlatform) {
                        /* 如果不是wayland平台, 则在qml中统计按键事件 */
                        bridge.handlePressed();
                    }
                    //==============================================

                    //==============================================
                    // 处理字符增删事件
                    //==============================================
                    if (growLength) {
                        bridge.handleCommittedText(committedText, growLength);
                    }
                    //==============================================
                }

                root.lastText = currentText;
            }
        }
    }
}
