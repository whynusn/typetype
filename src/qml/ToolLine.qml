// qml/ToolLine.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Pane {
    id: root

    property alias bridge: rowLayout.bridge
    property alias fontSize: rowLayout.fontSize
    property alias fontFamily: rowLayout.fontFamily
    property var textSourceOptions: []
    property string defaultTextSourceKey: ""

    signal requestLoadText(string sourceKey)
    signal requestLoadTextFromClipboard // 定义从剪贴板载文信号
    signal requestRetype

    // 自定义 Pane 的背景
    background: Rectangle {
        color: "#d3d3d3" // 灰色背景
        // 圆角
        radius: 2
        // 边框
        border.color: "#b0b0b0"
        border.width: 1
    }

    Row {
        id: rowLayout
        anchors.fill: parent
        spacing: 15

        property int fontSize: 14
        property string fontFamily: ""
        property var bridge: null  // 将外部 Bridge 传进来使用（可选）

        Image {
            source: "qrc:/resources/images/TypeTypeLogo.png"   // 如果用 Qt 资源系统
            // source: "images/logo.png"     // 或者直接用相对路径
            // source: "file:///absolute/path/to/logo.png"  // 也可以用绝对路径
            //width: 128
            height: 60
            anchors.verticalCenter: parent.verticalCenter
            fillMode: Image.PreserveAspectFit   // 保持宽高比，不会变形
        }

        ComboBox {
            id: sourceSelector
            width: 140
            model: root.textSourceOptions
            textRole: "label"
            valueRole: "key"
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: rowLayout.fontSize
            font.family: rowLayout.fontFamily
            height: 45

            contentItem: Text {
                leftPadding: 16
                rightPadding: sourceSelector.indicator.width + sourceSelector.spacing - 20
                text: sourceSelector.displayText
                font.pixelSize: rowLayout.fontSize
                font.family: rowLayout.fontFamily
                color: sourceSelector.enabled ? "#202020" : "#9a9a9a"
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }

            /* 下拉后每个子项的样式 */
            delegate: ItemDelegate {
                leftPadding: 0
                width: sourceSelector.width
                height: sourceSelector.height
                contentItem: Text {
                    text: sourceSelector.textAt(index)
                    font.pixelSize: rowLayout.fontSize
                    font.family: rowLayout.fontFamily
                    color: "#202020"
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
            }

            Component.onCompleted: {
                if (!root.defaultTextSourceKey)
                    return;
                /* 遍历找到默认项的索引 */
                for (var i = 0; i < model.length; i++) {
                    if (model[i].key === root.defaultTextSourceKey) {
                        currentIndex = i;
                        break;
                    }
                }
            }
        }

        RoundButton {
            id: loadText
            font.pixelSize: rowLayout.fontSize
            font.family: rowLayout.fontFamily
            width: 140
            height: 45
            //radius: 10
            text: "载文"
            onClicked: {
                root.requestLoadText(sourceSelector.currentValue);
            }
            anchors.verticalCenter: parent.verticalCenter
        }

        RoundButton {
            id: clipboardLoadText
            font.pixelSize: rowLayout.fontSize
            font.family: rowLayout.fontFamily
            width: 140
            height: 45
            //radius: 10
            text: "剪贴板载文"
            onClicked: {
                root.requestLoadTextFromClipboard();
            }
            anchors.verticalCenter: parent.verticalCenter
        }

        RoundButton {
            id: retype
            font.pixelSize: rowLayout.fontSize
            font.family: rowLayout.fontFamily
            width: 140
            height: 45
            //radius: 10
            text: "重打[F3]"
            onClicked: {
                root.requestRetype();
            }
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
