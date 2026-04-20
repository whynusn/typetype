// qml/LowerPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import RinUI as Rin

Pane {
    id: root
    property alias text: textArea.text
    property alias fontSize: textArea.font.pixelSize
    property alias fontFamily: textArea.font.family
    property alias isFocus: textArea.activeFocus
    //property alias textReadOnly: textArea.readOnly

    // 记录上一次的文本长度，用于计算增量
    property string lastText: ""
    property bool isSpecialPlatform: appBridge ? appBridge.isSpecialPlatform : false

    // 信号：通知 Bridge 焦点变化
    signal lowerPaneFocusChanged(bool hasFocus)

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
        }

        TextArea {
            id: textArea
            wrapMode: TextEdit.Wrap
            font.pixelSize: 14
            verticalAlignment: TextInput.AlignTop // 文字靠上
            width: scrollView.width // 宽度绑定到 scrollView，保证换行正确
            color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.textColor : "black"
            background: Rectangle {
                color: "transparent"
            }
            placeholderText: "请输入内容..."
            placeholderTextColor: "#999999"

            readOnly: appBridge ? appBridge.textReadOnly : true

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Backspace && appBridge && !appBridge.isSpecialPlatform) {
                    appBridge.accumulateBackspace();
                }
            }

            onActiveFocusChanged: {
                root.lowerPaneFocusChanged(activeFocus);
            }

            onCursorPositionChanged: {
                //console.log("cursorPosition =", cursorPosition);
                if (appBridge) {
                    appBridge.setCursorPos(cursorPosition);
                }
            }

            // ==========================================
            // 监听“正在输入的拼音/预编辑内容”
            // ==========================================
            /*
            onPreeditTextChanged: {
                // 这个参数就是输入法浮窗里显示的拼音（比如 "hao" 或 "hao ma"）
                //console.log("预编辑内容变化:", preeditText);
                if (preeditText === "") {
                    //console.log("这是空, 说明此时可能有上屏行为");
                }

                if (appBridge) {
                    // 你可以把拼音传给后端，做一些实时反馈（比如高亮匹配项）
                    //appBridge.handlePinyin(preeditText);
                }
            }
            */

            // ==========================================
            // 捕获上屏字符
            // ==========================================
            onTextChanged: {
                // if (appBridge) appBridge.onInputEnd();

                // 这里是你之前的“提取增量字符”的逻辑
                var currentText = text;
                // 注意：这里需要处理“用户删字”的情况
                var startPos = textArea.cursorPosition;
                var growLength = currentText.length - root.lastText.length;
                if (growLength > 0)
                    startPos -= growLength;
                var committedText = currentText.substring(startPos);

                //console.log("textChanged!!\n");

                if (appBridge) {
                    //==============================================
                    // 处理按键事件
                    //==============================================
                    if (preeditText === '' && currentText === '') {
                        if (qmlDebug)
                            console.debug("typing.lowerPane.startStatus=false reason=empty_input");
                        appBridge.handleStartStatus(false);
                    } else if (!appBridge.isStart() && !appBridge.isReadOnly()) {
                        if (qmlDebug)
                            console.debug("typing.lowerPane.startStatus=true source=textChanged");
                        appBridge.handleStartStatus(true);
                        if (root.isSpecialPlatform) {
                            appBridge.handlePressed(); // 第一下按键别忘了统计, 后续按键由全局监听器统计
                        }
                    }

                    //console.log("平台特殊性已暴露到qml中：" + root.isSpecialPlatform);
                    if (!root.isSpecialPlatform) {
                        /* 如果不是wayland平台, 则在qml中统计按键事件 */
                        appBridge.handlePressed();
                    }
                    //==============================================

                    //==============================================
                    // 处理字符增删事件
                    //==============================================
                    if (growLength) {
                        appBridge.handleCommittedText(committedText, growLength);
                        if (growLength < 0) {
                            appBridge.accumulateCorrection();
                        }
                    }
                    //==============================================
                }

                root.lastText = currentText;
            }
        }
    }
}
