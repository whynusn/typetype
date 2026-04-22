import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI
import "../components"

Dialog {
    id: root

    modal: false
    dim: false
    title: "载文设置"
    standardButtons: Dialog.Cancel
    closePolicy: Popup.NoAutoClose

    width: 500
    height: 620

    // 供外部注入
    property var textSourceOptions: []
    property string defaultTextSourceKey: ""

    // 来源列表 Model（从 catalog 加载）
    ListModel {
        id: sourceListModel
    }

    // 文本列表 Model
    ListModel {
        id: textListModel
    }

    // 缓存文本列表原始数据（含 id）
    property var rawTextList: []

    // 同步 catalog 到 sourceListModel（参考 TextLeaderboardPage）
    function syncSourceOptions(catalog) {
        sourceListModel.clear();
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                sourceListModel.append(catalog[i]);
            }
            if (catalog.length > 0) {
                sourceComboBox.currentIndex = 0;
            }
        }
    }

    // Dialog 打开时加载 catalog
    onOpened: {
        if (appBridge) {
            appBridge.loadCatalog();
        }
        contentTextArea.text = "";
        textListModel.clear();
    }

    // 监听 catalog 和 textList 信号
    Connections {
        target: appBridge
        enabled: root.visible

        function onCatalogLoaded(catalog) {
            root.syncSourceOptions(catalog);
        }

        function onTextListLoaded(texts) {
            textListModel.clear();
            root.rawTextList = texts;
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i];
                textListModel.append({
                    id: t.id || 0,
                    title: t.title || "",
                    char_count: t.charCount || 0,
                    clientTextId: t.clientTextId || 0
                });
            }
            // 自动选中第一篇并获取内容
            if (texts.length > 0 && texts[0].id) {
                textListView.currentIndex = 0;
                appBridge.getTextContentById(texts[0].id);
            }
        }

        function onTextContentLoaded(content, title) {
            if (root.visible) {
                contentTextArea.text = content;
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
            sliceSize = text.length;
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
            if (fullText) {
                var srcIdx = sourceComboBox.currentIndex;
                var srcKey = (srcIdx >= 0 && srcIdx < sourceListModel.count)
                    ? sourceListModel.get(srcIdx).key : "";
                appBridge.loadFullText(text, srcKey);
            } else {
                appBridge.setupSliceMode(
                    text, sliceSize,
                    retypeEnabled, metric, operator, threshold, shuffle
                );
            }
        }
        root.close();
    }

    // ============================
    // 布局（可滚动）
    // ============================
    contentItem: ScrollView {
        id: scrollView
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ColumnLayout {
            width: scrollView.width
            spacing: 12

            // --- 文本内容输入 ---
            Frame {
                Layout.fillWidth: true
                Layout.preferredHeight: 160
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
                Layout.preferredHeight: 200
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
                            // 参考 TextLeaderboardPage：用 model.get() 取 key
                            var key = (currentIndex >= 0 && currentIndex < sourceListModel.count)
                                ? sourceListModel.get(currentIndex).key : "";
                            if (key && appBridge) {
                                textListModel.clear();
                                appBridge.loadTextList(key);
                            }
                        }
                    }

                    ListView {
                        id: textListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: textListModel
                        currentIndex: -1

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        Text {
                            anchors.centerIn: parent
                            text: "暂无文本"
                            font.pixelSize: 12
                            color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#999"
                            visible: textListModel.count === 0
                        }

                        delegate: Rectangle {
                            width: textListView.width
                            height: 36
                            radius: 4
                            property bool isSelected: textListView.currentIndex === index
                            color: isSelected
                                ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor + "20" : "#3399ff20")
                                : "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 4

                                Text {
                                    Layout.fillWidth: true
                                    text: model.title || ""
                                    elide: Text.ElideRight
                                    font.pixelSize: 13
                                    font.weight: isSelected ? Font.DemiBold : Font.Normal
                                    color: isSelected
                                        ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#3399ff")
                                        : (Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333")
                                }

                                Text {
                                    text: {
                                        var chars = model.char_count !== undefined ? model.char_count : "?";
                                        return chars + "字";
                                    }
                                    font.pixelSize: 11
                                    color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    textListView.currentIndex = index;
                                    // 点击文本 → 按 ID 获取完整内容
                                    if (index >= 0 && index < root.rawTextList.length) {
                                        var t = root.rawTextList[index];
                                        if (t.id && appBridge) {
                                            appBridge.getTextContentById(t.id);
                                        }
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
                            currentIndex: 1
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
                                    var m = [];
                                    for (var i = 20; i <= 300; i += 10) m.push(String(i));
                                    return m;
                                } else if (metricCombo.currentIndex === 1) {
                                    var m2 = [];
                                    for (var j = 50; j <= 100; j += 5) m2.push(String(j));
                                    return m2;
                                } else {
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

            // 底部间距
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 4
            }
        }
    }
}
