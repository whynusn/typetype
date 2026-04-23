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

    readonly property string localGroupKey: "__local__"
    property var localSourceOptions: []
    property var catalogSourceOptions: []
    property string selectedSourceKey: ""
    property int pendingRemoteTextId: 0
    property bool syncingContentText: false
    property string validationMessage: ""

    readonly property int contentLength: contentTextArea.text.trim().length

    // 来源列表 Model（本地分组 + 远程来源）
    ListModel {
        id: sourceListModel
    }

    // 文本列表 Model
    ListModel {
        id: textListModel
    }

    function syncSourceOptions(options, catalogOptions) {
        root.localSourceOptions = [];
        sourceListModel.clear();
        if (options) {
            for (var i = 0; i < options.length; i++) {
                var option = options[i];
                if (option.isLocal) {
                    root.localSourceOptions.push(option);
                }
            }
        }

        if (root.localSourceOptions.length > 0) {
            sourceListModel.append({
                key: root.localGroupKey,
                label: "本地文本",
                isLocalGroup: true
            });
        }

        if (catalogOptions) {
            for (var j = 0; j < catalogOptions.length; j++) {
                var catalogOption = catalogOptions[j];
                if (catalogOption.key && catalogOption.key !== root.localGroupKey) {
                    sourceListModel.append(catalogOption);
                }
            }
        }

        root.restoreDefaultSourceSelection();
    }

    function refreshSourceOptions() {
        root.syncSourceOptions(textSourceOptions, root.catalogSourceOptions);
    }

    function updateCatalogOptions(catalog) {
        root.catalogSourceOptions = [];
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                var item = catalog[i];
                if (item.key) {
                    root.catalogSourceOptions.push({
                        key: item.key,
                        label: item.label || item.key
                    });
                }
            }
        }
        root.refreshSourceOptions();
    }

    function restoreDefaultSourceSelection() {
        var targetIndex = sourceListModel.count > 0 ? 0 : -1;
        var defaultKey = root.defaultTextSourceKey;
        if (defaultKey) {
            if (root.findLocalSourceIndex(defaultKey) >= 0 && root.localSourceOptions.length > 0) {
                targetIndex = 0;
            } else {
                for (var i = 0; i < sourceListModel.count; i++) {
                    if (sourceListModel.get(i).key === defaultKey) {
                        targetIndex = i;
                        break;
                    }
                }
            }
        }
        var previousIndex = sourceComboBox.currentIndex;
        sourceComboBox.currentIndex = targetIndex;
        if (previousIndex === targetIndex) {
            root.applySourceSelection(targetIndex);
        }
    }

    function findLocalSourceIndex(sourceKey) {
        for (var i = 0; i < root.localSourceOptions.length; i++) {
            if (root.localSourceOptions[i].key === sourceKey) {
                return i;
            }
        }
        return -1;
    }

    function resetSelectionState() {
        root.selectedSourceKey = "";
        root.pendingRemoteTextId = 0;
        root.setContentText("");
        textListModel.clear();
        textListView.currentIndex = -1;
    }

    function setContentText(text) {
        root.syncingContentText = true;
        contentTextArea.text = text;
        root.syncingContentText = false;
        root.refreshValidationMessage();
    }

    function sliceSizeMin() {
        return 1;
    }

    function sliceSizeMax() {
        return Math.max(1, root.contentLength);
    }

    function thresholdMin() {
        if (metricCombo.currentValue === "wrong_char_count") {
            return 0;
        }
        return 1;
    }

    function thresholdMax() {
        if (metricCombo.currentValue === "accuracy") {
            return 100;
        }
        if (metricCombo.currentValue === "wrong_char_count") {
            return Math.max(0, root.contentLength);
        }
        return 999;
    }

    function defaultThresholdText() {
        if (metricCombo.currentValue === "accuracy") {
            return "95";
        }
        if (metricCombo.currentValue === "wrong_char_count") {
            return "0";
        }
        return "60";
    }

    function sliceSizeValue() {
        return parseInt(sliceSizeField.text.trim());
    }

    function thresholdValue() {
        return parseInt(thresholdField.text.trim());
    }

    function ensureThresholdInRange() {
        var threshold = root.thresholdValue();
        if (!Number.isInteger(threshold) || threshold < root.thresholdMin() || threshold > root.thresholdMax()) {
            thresholdField.text = root.defaultThresholdText();
        }
    }

    function buildValidationMessage() {
        if (root.contentLength === 0) {
            return "";
        }

        if (!fullTextCheck.checked) {
            var sliceSize = root.sliceSizeValue();
            if (!Number.isInteger(sliceSize)) {
                return "每片字数必须是整数";
            }
            if (sliceSize < root.sliceSizeMin() || sliceSize > root.sliceSizeMax()) {
                return "每片字数必须在 1 到文章字数之间";
            }
        }

        if (retypeCheck.checked) {
            var threshold = root.thresholdValue();
            if (!Number.isInteger(threshold)) {
                return "重打阈值必须是整数";
            }
            if (threshold < root.thresholdMin() || threshold > root.thresholdMax()) {
                return root.thresholdHelperText();
            }
        }

        return "";
    }

    function refreshValidationMessage() {
        root.validationMessage = root.buildValidationMessage();
    }

    function thresholdHelperText() {
        if (metricCombo.currentValue === "accuracy") {
            return "准确率阈值必须在 1 到 100 之间";
        }
        if (metricCombo.currentValue === "wrong_char_count") {
            return "错字数阈值必须在 0 到文章字数之间";
        }
        return "速度阈值必须在 1 到 999 之间";
    }

    function loadLocalSourceList(preferredKey) {
        root.resetSelectionState();
        for (var i = 0; i < root.localSourceOptions.length; i++) {
            var localOption = root.localSourceOptions[i];
            var localContent = appBridge ? appBridge.getLocalTextContent(localOption.key) : "";
            textListModel.append({
                id: 0,
                title: localOption.label,
                sourceKey: localOption.key,
                char_count: localContent.length,
                isLocal: true
            });
        }

        if (textListModel.count === 0) {
            return;
        }

        var targetIndex = preferredKey ? root.findLocalSourceIndex(preferredKey) : 0;
        if (targetIndex < 0) {
            targetIndex = 0;
        }
        root.selectTextEntry(targetIndex);
    }

    function applySourceSelection(index) {
        var key = (index >= 0 && index < sourceListModel.count) ? sourceListModel.get(index).key : "";
        if (!key) {
            root.resetSelectionState();
            return;
        }
        if (key === root.localGroupKey) {
            root.loadLocalSourceList(root.defaultTextSourceKey);
        } else if (appBridge) {
            root.resetSelectionState();
            appBridge.loadTextList(key);
        }
    }

    function selectTextEntry(index) {
        if (index < 0 || index >= textListModel.count) {
            return;
        }

        textListView.currentIndex = index;
        var item = textListModel.get(index);
        if (item.isLocal) {
            root.pendingRemoteTextId = 0;
            root.selectedSourceKey = item.sourceKey || "";
            root.setContentText(appBridge ? appBridge.getLocalTextContent(root.selectedSourceKey) : "");
            return;
        }

        root.selectedSourceKey = item.sourceKey || "";
        root.pendingRemoteTextId = item.id || 0;
        if (root.pendingRemoteTextId > 0 && appBridge) {
            appBridge.getTextContentById(root.pendingRemoteTextId);
        }
    }

    onOpened: {
        root.setContentText("");
        root.validationMessage = "";
        sliceSizeField.text = "30";
        thresholdField.text = root.defaultThresholdText();
        root.refreshSourceOptions();
        if (appBridge) {
            appBridge.loadCatalog();
        }
    }

    // 监听 catalog 和 textList 信号
    Connections {
        target: appBridge
        enabled: root.visible

        function onCatalogLoaded(catalog) {
            root.updateCatalogOptions(catalog);
        }

        function onCatalogLoadFailed(message) {
            root.updateCatalogOptions([]);
        }

        function onTextListLoaded(texts) {
            var currentOption = sourceComboBox.currentIndex >= 0 && sourceComboBox.currentIndex < sourceListModel.count ? sourceListModel.get(sourceComboBox.currentIndex) : null;
            if (!currentOption || currentOption.key === root.localGroupKey) {
                return;
            }

            textListModel.clear();
            for (var i = 0; i < texts.length; i++) {
                var t = texts[i];
                textListModel.append({
                    id: t.id || 0,
                    title: t.title || "",
                    char_count: t.charCount !== undefined && t.charCount !== null ? t.charCount : -1,
                    clientTextId: t.clientTextId || 0,
                    sourceKey: currentOption.key,
                    isLocal: false
                });
            }

            if (texts.length > 0) {
                root.selectTextEntry(0);
            }
        }

        function onTextContentLoaded(textId, content, title) {
            if (root.visible && textId === root.pendingRemoteTextId) {
                root.setContentText(content);
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
        if (!text)
            return;

        root.refreshValidationMessage();
        if (root.validationMessage) {
            return;
        }

        var sliceSize = root.sliceSizeValue();
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
            threshold = root.thresholdValue();
            shuffle = shuffleCheck.checked;
        }

        if (appBridge) {
            if (fullText && !retypeEnabled) {
                appBridge.loadFullText(text, root.selectedSourceKey);
            } else {
                appBridge.setupSliceMode(text, sliceSize, retypeEnabled, metric, operator, threshold, shuffle);
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
                            onTextChanged: {
                                if (!root.syncingContentText && activeFocus) {
                                    root.selectedSourceKey = "";
                                    root.pendingRemoteTextId = 0;
                                }
                            }
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

                    Text {
                        text: sourceComboBox.currentValue === root.localGroupKey ? "“本地文本”会列出离线可用的内置文本，未联网时也能直接载文。" : "其余来源来自服务端文本目录，交互与“文本排行”页面保持一致。"
                        wrapMode: Text.Wrap
                        font.pixelSize: 11
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                    }

                    ComboBox {
                        id: sourceComboBox
                        Layout.fillWidth: true
                        model: sourceListModel
                        textRole: "label"
                        valueRole: "key"
                        onCurrentIndexChanged: {
                            root.applySourceSelection(currentIndex);
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
                            color: isSelected ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor + "20" : "#3399ff20") : "transparent"

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
                                    color: isSelected ? (Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#3399ff") : (Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333")
                                }

                                Text {
                                    text: model.char_count !== undefined && model.char_count >= 0 ? (model.char_count + "字") : ""
                                    font.pixelSize: 11
                                    color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.selectTextEntry(index);
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

                        TextField {
                            id: sliceSizeField
                            Layout.preferredWidth: 88
                            text: "30"
                            enabled: !fullTextCheck.checked
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: IntValidator {
                                bottom: root.sliceSizeMin()
                                top: root.sliceSizeMax()
                            }
                            onTextChanged: root.refreshValidationMessage()
                        }

                        Text {
                            text: fullTextCheck.checked ? "全文载入时固定为文章全文" : "输入 1 到 " + root.sliceSizeMax() + "的正整数"
                            font.pixelSize: 11
                            color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                            enabled: !fullTextCheck.checked
                        }

                        CheckBox {
                            id: fullTextCheck
                            text: "全文载入（不分片）"
                            onCheckedChanged: root.refreshValidationMessage()
                        }

                        Item {
                            Layout.fillWidth: true
                        }
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
                            onCheckedChanged: root.refreshValidationMessage()
                        }

                        Item {
                            Layout.fillWidth: true
                        }
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
                                ListElement {
                                    text: "速度(CPM)"
                                    value: "speed"
                                }
                                ListElement {
                                    text: "准确率(%)"
                                    value: "accuracy"
                                }
                                ListElement {
                                    text: "错字数"
                                    value: "wrong_char_count"
                                }
                            }
                            textRole: "text"
                            valueRole: "value"
                            onCurrentIndexChanged: {
                                root.ensureThresholdInRange();
                                root.refreshValidationMessage();
                            }
                        }

                        ComboBox {
                            id: operatorCombo
                            model: ListModel {
                                ListElement {
                                    text: "<"
                                    value: "lt"
                                }
                                ListElement {
                                    text: "≤"
                                    value: "le"
                                }
                                ListElement {
                                    text: "≥"
                                    value: "ge"
                                }
                                ListElement {
                                    text: ">"
                                    value: "gt"
                                }
                            }
                            textRole: "text"
                            valueRole: "value"
                        }

                        TextField {
                            id: thresholdField
                            Layout.preferredWidth: 88
                            text: "60"
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: IntValidator {
                                bottom: root.thresholdMin()
                                top: root.thresholdMax()
                            }
                            onTextChanged: root.refreshValidationMessage()
                        }

                        Text {
                            text: "时重打"
                            font.pixelSize: 13
                            color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                        }

                        Item {
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        visible: retypeCheck.checked
                        text: root.thresholdHelperText()
                        font.pixelSize: 11
                        color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                    }

                    CheckBox {
                        id: shuffleCheck
                        text: "重打时乱序"
                        visible: retypeCheck.checked
                    }
                }
            }

            Text {
                visible: root.validationMessage !== ""
                text: root.validationMessage
                font.pixelSize: 11
                color: Theme.currentTheme ? Theme.currentTheme.colors.systemCriticalColor : "#d13438"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            // --- 开始按钮 ---
            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                text: "开始载文"
                enabled: contentTextArea.text.trim().length > 0 && root.validationMessage === ""
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
