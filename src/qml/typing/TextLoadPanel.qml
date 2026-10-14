import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

/**
 * 自定义文本输入面板（载文中心「自定义」tab 专用）。
 *
 * 仅承载「粘贴/输入文本 + 乱序」。来源选择与分片设置由 hub 页面的
 * 共享组件承担（历史遗留的 compactMode/hubMode 双模式已收敛删除）。
 */
Item {
    id: root
    implicitHeight: contentColumn.implicitHeight

    // --- Outputs ---
    readonly property string contentText: contentTextArea.text.trim()
    readonly property int contentLength: contentText.length

    // 自定义文本无来源；保留属性维持 hub 调用契约（恒空，hub 走自定义兜底）
    readonly property string selectedSourceKey: ""
    readonly property string selectedSourceLabel: ""

    ColumnLayout {
        id: contentColumn
        width: parent.width
        spacing: 12

        // --- 文本内容输入 ---
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 160
            radius: Utils.radiusControl
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: qsTr("文本内容")
                        font.bold: true
                        typography: Typography.Body
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : Utils.fallbackTextColor
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: qsTr("乱序")
                        onClicked: {
                            var t = contentTextArea.text;
                            if (t.length > 0) {
                                var arr = t.split('');
                                for (var i = arr.length - 1; i > 0; i--) {
                                    var j = Math.floor(Math.random() * (i + 1));
                                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                                }
                                contentTextArea.text = arr.join('');
                            }
                        }
                    }
                }

                QQC.ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    TextArea {
                        id: contentTextArea
                        placeholderText: qsTr("在此输入或粘贴文本...")
                        wrapMode: TextArea.Wrap
                        selectByMouse: true
                        // RinUI TextArea 无 typography 属性（仅 Text/TextInput 有），直接设字号
                        font.pixelSize: Theme.currentTheme.typography.bodyLargeSize
                    }
                }
            }
        }
    }
}
