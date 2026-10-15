// qml/LowerPane.qml
import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import RinUI as Rin

QQC.Pane {
    id: root
    property alias text: textArea.text
    property alias fontSize: textArea.font.pixelSize
    property alias fontFamily: textArea.font.family
    property alias isFocus: textArea.activeFocus
    //property alias textReadOnly: textArea.readOnly

    // 记录上一次的文本长度，用于计算增量
    property string lastText: ""
    property bool isSpecialPlatform: appBridge ? appBridge.isSpecialPlatform : false
    // 程序化设置文本时为 true，抑制 onTextChanged 中的统计逻辑
    property bool suppressTextChanged: false

    // 信号：通知 Bridge 焦点变化
    signal lowerPaneFocusChanged(bool hasFocus)

    // 把键盘焦点交回输入区。
    //
    // 为什么要显式做：从别的页面切回跟打页时，焦点仍停在导航项上，而
    // F2/F3/F4 这类快捷键挂在页面的 Keys.onPressed 上——焦点不在本页子树里，
    // 事件就到不了，用户看到的是"快捷键失灵"（必须先在输入区点一下才有效）。
    // 场景验收实测：切回后不点输入区直接按 F3，重打不生效。
    function focusInput() {
        if (!textArea.readOnly && textArea.enabled) textArea.forceActiveFocus()
    }

    background: Rectangle {
        color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.cardColor : Rin.Utils.fallbackSurfaceColor
        border.color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.dividerBorderColor : Rin.Utils.fallbackSecondaryTextColor
        border.width: 1
        radius: Rin.Utils.radiusSmall
    }

    QQC.ScrollView {
        id: scrollView
        anchors.fill: parent
        clip: true // 确保文字不超出 Pane 的边界

        // 在 Qt 6 中，ScrollBar 应该附加给 ScrollView
        QQC.ScrollBar.vertical: QQC.ScrollBar {
            policy: QQC.ScrollBar.AsNeeded
        }

        QQC.TextArea {
            id: textArea
            // 命名关键交互节点：自动化验收（tools/ui_probe）靠 objectName 稳定
            // 指认输入区——本项目 QML 习惯不设 objectName，靠类型/位置定位在
            // 打完锁定等状态切换后会失配（readOnly 一变角色就变了）。
            objectName: "typingInput"
            wrapMode: TextEdit.Wrap
            font.pixelSize: 14
            verticalAlignment: TextInput.AlignTop // 文字靠上
            width: scrollView.width // 宽度绑定到 scrollView，保证换行正确
            color: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.textColor : Rin.Utils.fallbackTextColor
            background: Rectangle {
                color: "transparent"
            }
            placeholderText: qsTr("请输入内容...")
            placeholderTextColor: Rin.Theme.currentTheme ? Rin.Theme.currentTheme.colors.textSecondaryColor : Rin.Utils.fallbackTertiaryTextColor

            // AI 流式生成期间也锁定输入：chunk 会持续覆盖 UpperPane，
            // 此时打字既对着旧文档计分、又会在生成完成时被静默清空。
            readOnly: appBridge ? (appBridge.textReadOnly || appBridge.aiTextLoading) : true

            onReadOnlyChanged: {
                if (!readOnly) {
                    root.lastText = text;
                }
            }

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    event.accepted = true;
                    if (appBridge)
                        appBridge.toggleTypingPause();
                    return;
                }
                if (event.key === Qt.Key_Backspace && appBridge && !appBridge.isSpecialPlatform) {
                    appBridge.accumulateBackspace();
                }
                // Ctrl+R/O/U/P 由 TypingPage 的 Shortcut（WindowShortcut）接管，此处只保留
                // 未被 Shortcut 声明的 V/L；同名分支会被 shortcut-override 遮蔽成死代码。
                var shortcutPressed = (event.modifiers & Qt.ControlModifier) || (event.modifiers & Qt.MetaModifier);
                if (shortcutPressed) {
                    if (event.key === Qt.Key_V) {
                        event.accepted = true;
                        if (appBridge)
                            appBridge.loadTextFromClipboard();
                    } else if (event.key === Qt.Key_L) {
                        event.accepted = true;
                        if (appBridge)
                            appBridge.requestShuffle();
                    }
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
                // 程序化设置文本时只更新 lastText，不触发统计逻辑
                var currentText = text;
                if (root.suppressTextChanged) {
                    root.lastText = currentText;
                    return;
                }

                // The backend scores a sequential suffix only. A middle-cursor edit
                // cannot be represented safely by that state machine, so restore the
                // previous text instead of submitting the whole tail as new input.
                if (textArea.cursorPosition < currentText.length) {
                    root.suppressTextChanged = true;
                    textArea.text = root.lastText;
                    root.suppressTextChanged = false;
                    textArea.cursorPosition = textArea.length;
                    return;
                }

                // 注意：这里需要处理"用户删字"的情况
                var startPos = textArea.cursorPosition;
                var growLength = currentText.length - root.lastText.length;
                if (growLength > 0)
                    startPos -= growLength;
                var committedText = currentText.substring(startPos);

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

    Rin.FocusIndicator {
        control: textArea
    }
}
