import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    id: uploadPage
    property bool active: false  // 由 NavigationView 注入
    title: qsTr("上传文本")

    property bool toLocal: true
    property bool toCloud: false

    ListModel {
        id: sourceListModel
    }

    function clearForm() {
        titleField.text = "";
        contentArea.text = "";
        sourceComboBox.currentIndex = 0;
        localCheckBox.checked = true;
        cloudCheckBox.checked = false;
        toLocal = true;
        toCloud = false;
        errorText.visible = false;
        errorText.text = "";
    }

    function syncSourceOptionsFromCatalog(catalog) {
        sourceListModel.clear();
        if (catalog) {
            for (var i = 0; i < catalog.length; i++) {
                sourceListModel.append(catalog[i]);
            }
        }
        if (sourceComboBox.currentIndex >= sourceListModel.count) {
            sourceComboBox.currentIndex = 0;
        }
    }

    onActiveChanged: {
        if (active && appBridge) {
            appBridge.loadCatalog();
        }
    }

    ColumnLayout {
        spacing: 16

        Text {
            typography: Typography.Body
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("填写以下信息以上传新的练习文本")
        }

        // 标题
        Text {
            typography: Typography.BodyStrong
            text: qsTr("标题")
        }

        TextField {
            id: titleField
            Layout.fillWidth: true
            placeholderText: qsTr("请输入文本标题")
        }

        // 来源
        Text {
            typography: Typography.BodyStrong
            text: qsTr("来源")
        }

        ComboBox {
            id: sourceComboBox
            Layout.fillWidth: true
            model: sourceListModel
            textRole: "label"
            valueRole: "key"
        }

        // 内容
        Text {
            typography: Typography.BodyStrong
            text: qsTr("内容")
        }

        TextArea {
            id: contentArea
            Layout.fillWidth: true
            Layout.minimumHeight: 200
            placeholderText: qsTr("请输入文本内容")
            wrapMode: TextArea.Wrap
        }

        // 上传目标
        Text {
            typography: Typography.BodyStrong
            text: qsTr("上传目标")
        }

        ColumnLayout {
            spacing: 4

            CheckBox {
                id: localCheckBox
                text: qsTr("本地文本库")
                checked: true
                onCheckedChanged: {
                    uploadPage.toLocal = checked;
                }
            }

            CheckBox {
                id: cloudCheckBox
                text: qsTr("云端（仅管理员）")
                enabled: appBridge ? appBridge.loggedin : false
                onCheckedChanged: {
                    uploadPage.toCloud = checked;
                }
            }
        }

        // 错误提示
        Text {
            id: errorText
            visible: false
            color: Theme.currentTheme.colors.systemCriticalColor
            typography: Typography.Caption
            Layout.fillWidth: true
            horizontalAlignment: Qt.AlignCenter
        }

        // 按钮区
        Item {
            Layout.fillHeight: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Item {
                Layout.fillWidth: true
            }

            Button {
                text: qsTr("取消")
                onClicked: {
                    clearForm();
                }
            }

            Button {
                id: uploadBtn
                text: qsTr("上传")
                highlighted: true
                onClicked: {
                    var title = titleField.text.trim();
                    var content = contentArea.text.trim();
                    if (!title) {
                        errorText.text = qsTr("请输入标题");
                        errorText.visible = true;
                        return;
                    }
                    if (!content) {
                        errorText.text = qsTr("请输入内容");
                        errorText.visible = true;
                        return;
                    }
                    if (!uploadPage.toLocal && !uploadPage.toCloud) {
                        errorText.text = qsTr("请至少选择一个上传目标");
                        errorText.visible = true;
                        return;
                    }
                    errorText.visible = false;
                    uploadBtn.enabled = false;
                    var sourceKey = sourceComboBox.currentValue;
                    if (appBridge)
                        appBridge.uploadText(title, content, sourceKey, uploadPage.toLocal, uploadPage.toCloud);
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null
        function onUploadResult(success, message, textId) {
            uploadBtn.enabled = true;
            if (success) {
                clearForm();
                // 成功提示
                errorText.text = qsTr("上传成功");
                errorText.color = Theme.currentTheme.colors.systemSuccessColor;
                errorText.visible = true;
            } else {
                errorText.text = message;
                errorText.color = Theme.currentTheme.colors.systemCriticalColor;
                errorText.visible = true;
            }
        }
        function onLoggedinChanged() {
            if (appBridge && !appBridge.loggedin) {
                uploadPage.toCloud = false;
                cloudCheckBox.checked = false;
            }
        }
        function onCatalogLoaded(catalog) {
            syncSourceOptionsFromCatalog(catalog);
        }
    }
}
