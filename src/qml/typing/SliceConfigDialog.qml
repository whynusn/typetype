import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../components"

Dialog {
    id: root

    modal: true
    title: "载文设置"
    standardButtons: Dialog.Cancel
    closePolicy: Popup.NoAutoClose

    width: 480
    height: 600

    // 供外部注入
    property var textSourceOptions: []
    property string defaultTextSourceKey: ""

    // 来源列表 Model
    ListModel {
        id: sourceListModel
    }

    // 文本列表 Model
    ListModel {
        id: textListModel
    }

    onTextSourceOptionsChanged: {
        sourceListModel.clear();
        for (var i = 0; i < textSourceOptions.length; i++) {
            sourceListModel.append(textSourceOptions[i]);
        }
        if (defaultTextSourceKey) {
            for (var j = 0; j < sourceListModel.count; j++) {
                if (sourceListModel.get(j).key === defaultTextSourceKey) {
                    sourceComboBox.currentIndex = j;
                    break;
                }
            }
        }
    }

    // 当前选中的文本内容
    property string selectedTextContent: ""

    // 加载文本列表
    function loadTextListForSource(sourceKey) {
        textListModel.clear();
        selectedTextContent = "";
        if (appBridge) {
            appBridge.loadTextList(sourceKey);
        }
    }

    // 监听 textListLoaded 信号
    Connections {
        target: appBridge
        enabled: root.visible

        function onTextListLoaded(texts) {
            textListModel.clear();
            for (var i = 0; i < texts.length; i++) {
                textListModel.append(texts[i]);
            }
            // 自动选中第一项
            if (texts.length > 0 && appBridge) {
                appBridge.requestLoadText(
                    sourceComboBox.currentValue || root.defaultTextSourceKey
                );
            }
        }

        function onTextLoaded(text, textId, sourceLabel) {
            // 载文 Dialog 打开时收到 textLoaded → 填充 TextArea
            if (root.visible) {
                contentTextArea.text = text;
                selectedTextContent = text;
            }
        }
    }

    // 取消按钮关闭
    onRejected: {
        root.close();
    }

    // 开始载文
    function startSliceTyping() {
        var text = contentTextArea.text.trim();
        if (!text) return;

        var sliceSize = parseInt(sliceSizeCombo.currentText);
        var fullText = fullTextCheck.checked;

        if (fullText) {
            sliceSize = text.length; // 不分片
        }

        var retypeEnabled = retypeCheck.checked;
        var metric = "";
        var operator = "";
        var threshold = 0;
        var shuffle = false;

        if (retypeEnabled) {
            metric = metricCombo.currentValue;
            operator = operatorCombo.currentValue;
            threshold = parseFloat(thresholdCombo.currentText);
            shuffle = shuffleCheck.checked;
        }

        if (appBridge) {
            appBridge.setupSliceMode(
                text, sliceSize,
                retypeEnabled, metric, operator, threshold, shuffle
            );
        }
        root.close();
    }

    // ============================
    // 布局
    // ============================
    contentItem: ColumnLayout {
        spacing: 12

        // --- 文本内容输入 ---
        Frame {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 120
            radius: 6
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Text {
                    text: "文本内容"
                    font.bold: true
                    font.pixelSize: 13
                    color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    TextArea {
                        id: contentTextArea
                        placeholderText: "在此输入或粘贴文本，也可从下方文本库选择..."
                        wrapMode: TextArea.Wrap
                        selectByMouse: true
                        font.pixelSize: 14
                    }
                }
            }
        }

        // --- 从文本库选择 ---
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 180
            radius: 6
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Text {
                    text: "从文本库选择"
                    font.bold: true
                    font.pixelSize: 13
                    color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                }

                ComboBox {
                    id: sourceComboBox
                    Layout.fillWidth: true
                    model: sourceListModel
                    textRole: "label"
                    valueRole: "key"
                    onCurrentIndexChanged: {
                        var idx = currentIndex;
                        var key = (idx >= 0 && idx < sourceListModel.count)
                            ? sourceListModel.get(idx).key : "";
                        if (key) {
                            root.loadTextListForSource(key);
                        }
                    }
                }

                ListView {
                    id: textListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: textListModel

                    delegate: Rectangle {
                        width: textListView.width
                        height: 32
                        color: textListView.currentIndex === index
                            ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor + "30" : "#3399ff30")
                            : "transparent"
                        radius: 4

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8

                            Text {
                                Layout.fillWidth: true
                                text: model.title || ""
                                elide: Text.ElideRight
                                font.pixelSize: 13
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                            }

                            Text {
                                text: (model.charCount || 0) + "字"
                                font.pixelSize: 12
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                textListView.currentIndex = index;
                                // 点击文本列表项 → 预览加载文本到 TextArea
                                if (appBridge) {
                                    var sourceKey = sourceListModel.get(sourceComboBox.currentIndex).key;
                                    appBridge.requestLoadTextForPreview(sourceKey);
                                }
                            }
                        }
                    }
                }
            }
        }

        // --- 分片设置 ---
        Frame {
            Layout.fillWidth: true
            implicitHeight: sliceSettingsColumn.implicitHeight + 24
            radius: 6
            hoverable: false

            ColumnLayout {
                id: sliceSettingsColumn
                anchors.fill: parent
                spacing: 8

                Text {
                    text: "分片设置"
                    font.bold: true
                    font.pixelSize: 13
                    color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Text {
                        text: "每片字数:"
                        font.pixelSize: 13
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                    }

                    ComboBox {
                        id: sliceSizeCombo
                        model: ["20", "30", "50", "80", "100", "150", "200"]
                        currentIndex: 1  // 默认 30
                        enabled: !fullTextCheck.checked
                    }

                    CheckBox {
                        id: fullTextCheck
                        text: "全文载入（不分片）"
                    }

                    Item { Layout.fillWidth: true }
                }
            }
        }

        // --- 重打条件 ---
        Frame {
            Layout.fillWidth: true
            implicitHeight: retypeColumn.implicitHeight + 24
            radius: 6
            hoverable: false

            ColumnLayout {
                id: retypeColumn
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true

                    CheckBox {
                        id: retypeCheck
                        text: "开启重打条件"
                    }

                    Item { Layout.fillWidth: true }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: retypeCheck.checked

                    Text {
                        text: "当"
                        font.pixelSize: 13
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                    }

                    ComboBox {
                        id: metricCombo
                        model: ListModel {
                            ListElement { text: "速度(CPM)"; value: "speed" }
                            ListElement { text: "准确率(%)"; value: "accuracy" }
                            ListElement { text: "错字数"; value: "wrong_char_count" }
                        }
                        textRole: "text"
                        valueRole: "value"
                    }

                    ComboBox {
                        id: operatorCombo
                        model: ListModel {
                            ListElement { text: "<"; value: "lt" }
                            ListElement { text: "≤"; value: "le" }
                            ListElement { text: "≥"; value: "ge" }
                            ListElement { text: ">"; value: "gt" }
                        }
                        textRole: "text"
                        valueRole: "value"
                    }

                    ComboBox {
                        id: thresholdCombo
                        model: {
                            if (metricCombo.currentIndex === 0) {
                                // 速度: 20-300
                                var m = [];
                                for (var i = 20; i <= 300; i += 10) m.push(String(i));
                                return m;
                            } else if (metricCombo.currentIndex === 1) {
                                // 准确率: 50-100
                                var m2 = [];
                                for (var j = 50; j <= 100; j += 5) m2.push(String(j));
                                return m2;
                            } else {
                                // 错字数: 0-50
                                var m3 = [];
                                for (var k = 0; k <= 50; k += 1) m3.push(String(k));
                                return m3;
                            }
                        }
                        currentIndex: metricCombo.currentIndex === 0 ? 4 : (metricCombo.currentIndex === 1 ? 6 : 0)
                    }

                    Text {
                        text: "时重打"
                        font.pixelSize: 13
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                    }

                    Item { Layout.fillWidth: true }
                }

                CheckBox {
                    id: shuffleCheck
                    text: "重打时乱序"
                    visible: retypeCheck.checked
                }
            }
        }

        // --- 开始按钮 ---
        Button {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            text: "开始载文"
            enabled: contentTextArea.text.trim().length > 0
            onClicked: root.startSliceTyping()
        }
    }
}
