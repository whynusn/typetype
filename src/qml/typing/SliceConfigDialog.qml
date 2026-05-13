import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI
import "../components"

Dialog {
    id: root

    modal: false
    dim: false
    title: "载文设置"
    closePolicy: Popup.NoAutoClose

    width: 500
    height: 720

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

    function sliceSizeValue() {
        return parseInt(sliceSizeField.text.trim());
    }

    function buildValidationMessage() {
        if (root.contentLength === 0) {
            return "";
        }

        if (sliceModeCheck.checked) {
            var sliceSize = root.sliceSizeValue();
            if (!Number.isInteger(sliceSize)) {
                return "每片字数必须是整数";
            }
            if (sliceSize < root.sliceSizeMin() || sliceSize > root.sliceSizeMax()) {
                return "每片字数必须在 1 到文章字数之间";
            }

            var startSlice = parseInt(startSliceField.text.trim());
            if (!Number.isInteger(startSlice) || startSlice < 1) {
                return "开始片段必须是大于等于 1 的整数";
            }

            var totalSlices = Math.ceil(root.contentLength / sliceSize);
            if (startSlice > totalSlices) {
                return "开始片段不能超过总片段数 " + totalSlices;
            }
        }

        var keyStrokeMin = parseInt(keyStrokeMinSpin.value);
        if (!Number.isInteger(keyStrokeMin) || keyStrokeMin < 0 || keyStrokeMin > 999) {
            return "击键阈值必须在 0 到 999 之间";
        }

        var speedMin = parseInt(speedMinSpin.value);
        if (!Number.isInteger(speedMin) || speedMin < 0 || speedMin > 999) {
            return "速度阈值必须在 0 到 999 之间";
        }

        var accuracyMin = parseInt(accuracyMinSpin.value);
        if (!Number.isInteger(accuracyMin) || accuracyMin < 0 || accuracyMin > 100) {
            return "键准阈值必须在 0 到 100 之间";
        }

        var passCountMin = parseInt(passCountMinSpin.value);
        if (!Number.isInteger(passCountMin) || passCountMin < 1 || passCountMin > 9999) {
            return "达标次数必须在 1 到 9999 之间";
        }

        return "";
    }

    function refreshValidationMessage() {
        root.validationMessage = root.buildValidationMessage();
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
        sliceSizeField.text = "10";
        startSliceField.text = "1";
        keyStrokeMinSpin.value = 6;
        speedMinSpin.value = 100;
        accuracyMinSpin.value = 95;
        passCountMinSpin.value = 1;
        onFailActionCombo.currentIndex = 1; // 默认“重打”，避免默认乱序
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
        var fullText = !sliceModeCheck.checked;
        var openCondition = conditionCheck.checked && sliceModeCheck.checked;
        var startSlice = parseInt(startSliceField.text.trim());

        if (fullText) {
            sliceSize = text.length;
            startSlice = 1;
        }

        var keyStrokeMin = parseInt(keyStrokeMinSpin.value);
        var speedMin = parseInt(speedMinSpin.value);
        var accuracyMin = parseInt(accuracyMinSpin.value);
        var passCountMin = parseInt(passCountMinSpin.value);
        var onFailAction = onFailActionCombo.currentValue;

        if (appBridge) {
            // 先设置全部参数（含推进模式/全文乱序）
            appBridge.setSliceCriteria(
                keyStrokeMin, speedMin, accuracyMin, passCountMin,
                openCondition ? onFailAction : "none",
                advanceModeCombo.currentValue,
                fullShuffleCheck.checked
            );
            if (fullText) {
                appBridge.loadFullText(text, root.selectedSourceKey);
            } else {
                appBridge.setupSliceMode(text, sliceSize, startSlice, keyStrokeMin, speedMin, accuracyMin, passCountMin, openCondition ? onFailAction : "none");
            }
        }
        root.close();
    }

    // ============================
    // 布局（可滚动）
    // ============================
    contentItem: Item {
        id: contentWrapper

        Flickable {
            id: scrollView
            anchors.fill: parent
            clip: true
            contentWidth: width
            contentHeight: columnLayout.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            QQC.ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: columnLayout
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

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "文本内容"
                                font.bold: true
                                font.pixelSize: 13
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Button {
                                text: "乱序"
                                onClicked: {
                                    var text = contentTextArea.text;
                                    if (text.length > 0) {
                                        var arr = text.split('');
                                        for (var i = arr.length - 1; i > 0; i--) {
                                            var j = Math.floor(Math.random() * (i + 1));
                                            var tmp = arr[i];
                                            arr[i] = arr[j];
                                            arr[j] = tmp;
                                        }
                                        root.setContentText(arr.join(''));
                                    }
                                }
                            }
                        }

                        QQC.ScrollView {
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
                            boundsBehavior: Flickable.StopAtBounds
                            model: textListModel
                            currentIndex: -1

                            QQC.ScrollBar.vertical: ScrollBar {
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

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: "分片设置"
                                font.bold: true
                                font.pixelSize: 13
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            CheckBox {
                                id: sliceModeCheck
                                text: "开启"
                                onCheckedChanged: root.refreshValidationMessage()
                            }
                        }

                        RowLayout {
                            visible: sliceModeCheck.checked
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
                                text: "10"
                                enabled: sliceModeCheck.checked
                                inputMethodHints: Qt.ImhDigitsOnly
                                validator: IntValidator {
                                    bottom: root.sliceSizeMin()
                                    top: root.sliceSizeMax()
                                }
                                onTextChanged: root.refreshValidationMessage()
                            }

                            Text {
                                text: !sliceModeCheck.checked ? "全文载入" : "输入 1 到 " + root.sliceSizeMax() + "的正整数"
                                font.pixelSize: 11
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textSecondaryColor : "#666"
                                enabled: sliceModeCheck.checked
                            }

                            Text {
                                text: "开始片段:"
                                font.pixelSize: 13
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                            }

                            TextField {
                                id: startSliceField
                                Layout.preferredWidth: 72
                                text: "1"
                                enabled: sliceModeCheck.checked
                                inputMethodHints: Qt.ImhDigitsOnly
                                validator: IntValidator {
                                    bottom: 1
                                    top: 9999
                                }
                                onTextChanged: root.refreshValidationMessage()
                            }

                            Item {
                                Layout.fillWidth: true
                            }
                        }

                        // 全文乱序
                        RowLayout {
                            visible: sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: qsTr("全文乱序")
                                font.pixelSize: 13
                                color: Theme.currentTheme ? Theme.currentTheme.colors.textColor : "#333"
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            CheckBox {
                                id: fullShuffleCheck
                                text: qsTr("分片前打乱全文")
                            }
                        }
                    }
                }

                // --- 自动推进 ---
                Frame {
                    Layout.fillWidth: true
                    radius: 6
                    hoverable: false
                    padding: 8

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                typography: Typography.BodyStrong
                                text: qsTr("自动推进")
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            CheckBox {
                                id: conditionCheck
                                enabled: sliceModeCheck.checked
                                text: qsTr("开启")
                            }
                        }

                        Text {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            text: qsTr("每段达标后自动跳转下一段，达标条件与未达标行为如下：")
                            wrapMode: Text.Wrap
                        }

                        // 推进模式
                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                typography: Typography.Body
                                text: qsTr("推进模式")
                            }

                            ComboBox {
                                id: advanceModeCombo
                                model: ListModel {
                                    ListElement {
                                        text: qsTr("顺序下一段")
                                        value: "sequential"
                                    }
                                    ListElement {
                                        text: qsTr("随机下一段")
                                        value: "random"
                                    }
                                }
                                textRole: "text"
                                valueRole: "value"
                            }
                        }

                        // 达标条件
                        Text {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            typography: Typography.Body
                            text: qsTr("达标条件")
                        }

                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                typography: Typography.Body
                                text: qsTr("击键 ≥")
                            }
                            SpinBox {
                                id: keyStrokeMinSpin
                                Layout.preferredWidth: 128
                                Layout.preferredHeight: 34
                                from: 0
                                to: 99
                                value: 6
                                stepSize: 1
                                editable: true
                            }
                            Text {
                                typography: Typography.Caption
                                text: qsTr("次/秒")
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }

                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                typography: Typography.Body
                                text: qsTr("速度 ≥")
                            }
                            SpinBox {
                                id: speedMinSpin
                                Layout.preferredWidth: 128
                                Layout.preferredHeight: 34
                                from: 0
                                to: 999
                                value: 100
                                stepSize: 10
                                editable: true
                            }
                            Text {
                                typography: Typography.Caption
                                text: qsTr("字/分")
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }

                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                typography: Typography.Body
                                text: qsTr("键准 ≥")
                            }
                            SpinBox {
                                id: accuracyMinSpin
                                Layout.preferredWidth: 128
                                Layout.preferredHeight: 34
                                from: 0
                                to: 100
                                value: 95
                                stepSize: 5
                                editable: true
                            }
                            Text {
                                typography: Typography.Caption
                                text: "%"
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }

                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                typography: Typography.Body
                                text: qsTr("连达标 ≥")
                            }
                            SpinBox {
                                id: passCountMinSpin
                                Layout.preferredWidth: 128
                                Layout.preferredHeight: 34
                                from: 1
                                to: 99
                                value: 1
                                stepSize: 1
                                editable: true
                            }
                            Text {
                                typography: Typography.Caption
                                text: qsTr("次")
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }

                        Text {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            text: qsTr("击键、速度、键准均达标且无错字算一次合格")
                            wrapMode: Text.Wrap
                        }

                        RowLayout {
                            visible: conditionCheck.checked && sliceModeCheck.checked
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                typography: Typography.Body
                                text: qsTr("未达标/有错字")
                            }

                            ComboBox {
                                id: onFailActionCombo
                                model: ListModel {
                                    ListElement {
                                        text: qsTr("乱序重打")
                                        value: "shuffle"
                                    }
                                    ListElement {
                                        text: qsTr("重打")
                                        value: "retype"
                                    }
                                    ListElement {
                                        text: qsTr("无动作")
                                        value: "none"
                                    }
                                }
                                textRole: "text"
                                valueRole: "value"
                            }

                            Item {
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }
        }
    }

    footer: ColumnLayout {
        spacing: 0
        width: parent.width

        // 验证提示区域
        Text {
            visible: root.validationMessage !== ""
            text: root.validationMessage
            font.pixelSize: 11
            color: Theme.currentTheme ? Theme.currentTheme.colors.systemCriticalColor : "#d13438"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            Layout.topMargin: 8
            Layout.bottomMargin: 8
        }

        DialogButtonBox {
            Layout.fillWidth: true
            alignment: Qt.AlignRight
            padding: 24
            spacing: 8

            Button {
                text: "取消"
                QQC.DialogButtonBox.buttonRole: QQC.DialogButtonBox.RejectRole
                onClicked: root.reject()
            }
            Button {
                text: "开始载文"
                QQC.DialogButtonBox.buttonRole: QQC.DialogButtonBox.AcceptRole
                enabled: contentTextArea.text.trim().length > 0 && root.validationMessage === ""
                onClicked: root.startSliceTyping()
            }
        }
    }
}
