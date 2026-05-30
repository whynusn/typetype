import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

Item {
    id: root
    implicitHeight: contentColumn.implicitHeight

    // --- Inputs ---
    property var textSourceOptions: []
    property string defaultTextSourceKey: ""
    property var catalogSourceOptions: []
    property bool compactMode: false  // true: 隐藏来源选择器，仅保留切片设置

    // --- Outputs ---
    readonly property string contentText: contentTextArea.text.trim()
    property bool sliceModeChecked: sliceModeCheck.checked
    property int sliceSize: sliceSizeSpin.value
    property int startSlice: startSliceSpin.value
    property bool fullShuffleChecked: false

    readonly property int contentLength: contentTextArea.text.trim().length

    // 当前选中来源的显示标签
    readonly property string selectedSourceLabel: {
        if (textListView.currentIndex >= 0 && textListView.currentIndex < textListModel.count) {
            return textListModel.get(textListView.currentIndex).title || "";
        }
        return "";
    }

    // 总片段数
    readonly property int totalSlices: sliceSize > 0 ? Math.max(1, Math.ceil(contentLength / sliceSize)) : 1

    // textSourceOptions 外部变更时自动同步
    onTextSourceOptionsChanged: syncSourceOptions(textSourceOptions, catalogSourceOptions)

    function sliceSizeMin() { return 1; }
    function sliceSizeMax() { return Math.max(1, contentLength); }

    // 验证消息（仅校验切片参数，指标校验由 SliceCriteriaPanel 处理；SpinBox 已处理边界）
    readonly property string validationMessage: contentLength === 0 ? "" : ""

    // --- 内部状态 ---
    readonly property string localGroupKey: "__local__"
    property var localSourceOptions: []
    property string selectedSourceKey: ""
    property int pendingRemoteTextId: 0
    property bool syncingContentText: false

    ListModel { id: sourceListModel }
    ListModel { id: textListModel }

    function syncSourceOptions(options, catalog) {
        localSourceOptions = [];
        sourceListModel.clear();
        if (options) {
            for (var i = 0; i < options.length; i++) {
                if (options[i].isLocal) localSourceOptions.push(options[i]);
            }
        }
        if (localSourceOptions.length > 0) {
            sourceListModel.append({ key: localGroupKey, label: "本地文本", isLocalGroup: true });
        }
        if (catalog) {
            for (var j = 0; j < catalog.length; j++) {
                var item = catalog[j];
                if (item.key && item.key !== localGroupKey)
                    sourceListModel.append({ key: item.key, label: item.label || item.key });
            }
        }
        _restoreDefaultSource();
    }

    function _restoreDefaultSource() {
        var idx = 0;
        var dk = defaultTextSourceKey;
        if (dk) {
            if (findLocalSourceIndex(dk) >= 0 && localSourceOptions.length > 0) {
                idx = 0;
            } else {
                for (var i = 0; i < sourceListModel.count; i++) {
                    if (sourceListModel.get(i).key === dk) { idx = i; break; }
                }
            }
        }
        var prev = sourceComboBox.currentIndex;
        sourceComboBox.currentIndex = idx;
        if (prev === idx) _applySource(idx);
    }

    function findLocalSourceIndex(key) {
        for (var i = 0; i < localSourceOptions.length; i++)
            if (localSourceOptions[i].key === key) return i;
        return -1;
    }

    function reset() {
        selectedSourceKey = "";
        pendingRemoteTextId = 0;
        _setContentText("");
        textListModel.clear();
        textListView.currentIndex = -1;
    }

    function setContentText(text) { _setContentText(text); }

    function _setContentText(text) {
        syncingContentText = true;
        contentTextArea.text = text;
        syncingContentText = false;
    }

    function _loadLocalSourceList(preferredKey) {
        reset();
        for (var i = 0; i < localSourceOptions.length; i++) {
            var opt = localSourceOptions[i];
            var c = appBridge ? appBridge.getLocalTextContent(opt.key) : "";
            textListModel.append({ id: 0, title: opt.label, sourceKey: opt.key, char_count: c.length, isLocal: true });
        }
        if (textListModel.count === 0) return;
        var idx = preferredKey ? findLocalSourceIndex(preferredKey) : 0;
        if (idx < 0) idx = 0;
        _selectEntry(idx);
    }

    function _applySource(index) {
        var key = (index >= 0 && index < sourceListModel.count) ? sourceListModel.get(index).key : "";
        if (!key) { reset(); return; }
        if (key === localGroupKey)
            _loadLocalSourceList(defaultTextSourceKey);
        else if (appBridge) {
            reset();
            appBridge.loadTextList(key);
        }
    }

    function _selectEntry(index) {
        if (index < 0 || index >= textListModel.count) return;
        textListView.currentIndex = index;
        var item = textListModel.get(index);
        if (item.isLocal) {
            pendingRemoteTextId = 0;
            selectedSourceKey = item.sourceKey || "";
            _setContentText(appBridge ? appBridge.getLocalTextContent(selectedSourceKey) : "");
            return;
        }
        selectedSourceKey = item.sourceKey || "";
        pendingRemoteTextId = item.id || 0;
        if (pendingRemoteTextId > 0 && appBridge) appBridge.getTextContentById(pendingRemoteTextId);
    }

    // ====== UI ======

    ColumnLayout {
        id: contentColumn
        width: parent.width
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

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "文本内容"; font.bold: true; font.pixelSize: 13; color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333" }
                    Item { Layout.fillWidth: true }
                    Button {
                        visible: !root.compactMode
                        text: "乱序"
                        onClicked: {
                            var t = contentTextArea.text;
                            if (t.length > 0) {
                                var arr = t.split('');
                                for (var i = arr.length - 1; i > 0; i--) {
                                    var j = Math.floor(Math.random() * (i + 1));
                                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
                                }
                                _setContentText(arr.join(''));
                            }
                        }
                    }
                }

                QQC.ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    TextArea {
                        id: contentTextArea
                        placeholderText: "在此输入或粘贴文本，也可从下方文本库选择..."
                        wrapMode: TextArea.Wrap
                        selectByMouse: true
                        font.pixelSize: 14
                        onTextChanged: {
                            if (!syncingContentText && activeFocus) {
                                selectedSourceKey = "";
                                pendingRemoteTextId = 0;
                            }
                        }
                    }
                }
            }
        }

        // --- 从文本库选择 ---
        Frame {
            visible: !root.compactMode
            Layout.fillWidth: true
            Layout.preferredHeight: 200
            radius: 6
            hoverable: false

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Text { text: "从文本库选择"; font.bold: true; font.pixelSize: 13; color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333" }
                Text {
                    text: sourceComboBox.currentValue === localGroupKey
                        ? "“本地文本”会列出离线可用的内置文本，未联网时也能直接载文。"
                        : "其余来源来自服务端文本目录，交互与“文本排行”页面保持一致。"
                    wrapMode: Text.Wrap; font.pixelSize: 11
                    color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                }

                ComboBox {
                    id: sourceComboBox
                    Layout.fillWidth: true
                    model: sourceListModel
                    textRole: "label"
                    valueRole: "key"
                    onCurrentIndexChanged: _applySource(currentIndex)
                }

                ListView {
                    id: textListView
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    model: textListModel
                    currentIndex: -1
                    QQC.ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    Text {
                        anchors.centerIn: parent
                        text: "暂无文本"; font.pixelSize: 12
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#999"
                        visible: textListModel.count === 0
                    }

                    delegate: Rectangle {
                        width: textListView.width; height: 36; radius: 4
                        property bool isSelected: textListView.currentIndex === index
                        color: isSelected ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor + "20" : "#3399ff20") : "transparent"

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 4
                            Text {
                                Layout.fillWidth: true; text: model.title || ""; elide: Text.ElideRight
                                font.pixelSize: 13
                                font.weight: isSelected ? Font.DemiBold : Font.Normal
                                color: isSelected ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#3399ff") : (Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333")
                            }
                            Text {
                                text: model.char_count !== undefined && model.char_count >= 0 ? (model.char_count + "字") : ""
                                font.pixelSize: 11
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: _selectEntry(index)
                        }
                    }
                }
            }
        }

        // --- 分片设置 ---
        Frame {
            Layout.fillWidth: true
            radius: 6; hoverable: false; padding: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        text: qsTr("分片设置")
                        font.bold: true; font.pixelSize: 13
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: qsTr("共 %1 段").arg(root.totalSlices)
                        font.pixelSize: 11
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                    }

                    CheckBox {
                        id: sliceModeCheck
                        text: qsTr("开启")
                        checked: true
                    }
                }

                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 1
                    color: Theme.currentTheme.colors.cardBorderColor
                }

                // 每段字数
                RowLayout {
                    visible: sliceModeCheck.checked
                    Layout.fillWidth: true; Layout.preferredHeight: 42; spacing: 8

                    Text {
                        Layout.preferredWidth: 72
                        typography: Typography.Body
                        text: qsTr("每段字数")
                    }

                    SpinBox {
                        id: sliceSizeSpin
                        Layout.preferredWidth: 128; Layout.preferredHeight: 34
                        from: 1; to: 99999; value: 100; stepSize: 5; editable: true
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                        text: qsTr("共 %1 段").arg(root.totalSlices)
                        elide: Text.ElideRight
                    }
                }

                // 段序号
                RowLayout {
                    visible: sliceModeCheck.checked
                    Layout.fillWidth: true; Layout.preferredHeight: 42; spacing: 8

                    Text {
                        Layout.preferredWidth: 72
                        typography: Typography.Body
                        text: qsTr("段序号")
                    }

                    SpinBox {
                        id: startSliceSpin
                        Layout.preferredWidth: 128; Layout.preferredHeight: 34
                        from: 1; to: root.totalSlices; value: 1; editable: true
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                        text: qsTr("范围 1-%1").arg(startSliceSpin.to)
                        elide: Text.ElideRight
                    }
                }

                // 全文乱序
                RowLayout {
                    visible: sliceModeCheck.checked
                    Layout.fillWidth: true; spacing: 8
                    Text { text: qsTr("全文乱序"); font.pixelSize: 13; color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333" }
                    Item { Layout.fillWidth: true }
                    CheckBox {
                        text: qsTr("分片前打乱全文")
                        onCheckedChanged: root.fullShuffleChecked = checked
                    }
                }
            }
        }
    }

    // --- AppBridge 信号 ---
    function onCatalogLoaded(catalog) {
        catalogSourceOptions = [];
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                if (catalog[i].key)
                    catalogSourceOptions.push({ key: catalog[i].key, label: catalog[i].label || catalog[i].key });
            }
        }
        syncSourceOptions(textSourceOptions, catalogSourceOptions);
    }

    function onTextListLoaded(texts) {
        var currentOption = sourceComboBox.currentIndex >= 0 && sourceComboBox.currentIndex < sourceListModel.count
            ? sourceListModel.get(sourceComboBox.currentIndex) : null;
        if (!currentOption || currentOption.key === localGroupKey) return;
        textListModel.clear();
        for (var i = 0; i < texts.length; i++) {
            var t = texts[i];
            textListModel.append({ id: t.id || 0, title: t.title || "", char_count: t.charCount !== undefined ? t.charCount : -1, clientTextId: t.clientTextId || 0, sourceKey: currentOption.key, isLocal: false });
        }
        if (texts.length > 0) _selectEntry(0);
    }

    function onTextContentLoaded(textId, content, title) {
        if (visible && textId === pendingRemoteTextId) _setContentText(content);
    }
}
