// qml/ToolLine.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

Pane {
    id: root

    property var textSourceOptions: []
    property string defaultTextSourceKey: ""

    signal requestLoadText(string sourceKey)
    signal requestLoadTextFromClipboard // 定义从剪贴板载文信号
    signal requestRetype

    // 将 JS 数组转换为 ListModel，使 RinUI ContextMenu 能正确按 textRole 读取
    ListModel {
        id: sourceListModel
    }

    onTextSourceOptionsChanged: {
        sourceListModel.clear();
        for (var i = 0; i < textSourceOptions.length; i++) {
            sourceListModel.append(textSourceOptions[i]);
        }
        // 恢复默认选中项
        if (defaultTextSourceKey) {
            for (var j = 0; j < sourceListModel.count; j++) {
                if (sourceListModel.get(j).key === defaultTextSourceKey) {
                    sourceSelector.currentIndex = j;
                    break;
                }
            }
        }
    }

    // 自定义 Pane 的背景（跟随 RinUI 主题）
    background: Rectangle {
        color: Theme.currentTheme ? Theme.currentTheme.colors.cardColor : "#d3d3d3"
        radius: 2
        border.color: Theme.currentTheme ? Theme.currentTheme.colors.controlBorderColor : "#b0b0b0"
        border.width: 1
    }

    Row {
        id: rowLayout
        anchors.fill: parent
        spacing: 15

        Image {
            source: resourceBaseUrl + "images/TypeTypeLogo.png"
            height: 60
            anchors.verticalCenter: parent.verticalCenter
            fillMode: Image.PreserveAspectFit   // 保持宽高比，不会变形
        }

        ComboBox {
            id: sourceSelector
            width: 140
            model: sourceListModel
            textRole: "label"
            valueRole: "key"
            anchors.verticalCenter: parent.verticalCenter
            height: 45
        }

        RoundButton {
            id: loadText
            width: 140
            height: 45
            text: "载文"
            onClicked: {
                root.requestLoadText(sourceSelector.currentValue);
            }
            anchors.verticalCenter: parent.verticalCenter
        }

        RoundButton {
            id: clipboardLoadText
            width: 140
            height: 45
            text: "剪贴板载文"
            onClicked: {
                root.requestLoadTextFromClipboard();
            }
            anchors.verticalCenter: parent.verticalCenter
        }

        RoundButton {
            id: retype
            width: 140
            height: 45
            text: "重打[F3]"
            onClicked: {
                root.requestRetype();
            }
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
