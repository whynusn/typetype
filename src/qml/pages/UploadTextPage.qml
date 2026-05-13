import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

FluentPage {
    id: uploadPage
    property bool active: false  // 由 NavigationView 注入
    title: qsTr("上传文本")
    contentSpacing: 4

    property bool toLocal: true
    property bool toCloud: false
    property bool uploading: false

    function clearForm() {
        titleField.text = "";
        contentArea.text = "";
        localCheckBox.checked = true;
        cloudCheckBox.checked = false;
        toLocal = true;
        toCloud = false;
        infoBar.visible = false;
    }

    function showInfo(severity, title, text) {
        infoBar.severity = severity;
        infoBar.title = title;
        infoBar.text = text;
        infoBar.visible = true;
    }

    // 反馈提示
    InfoBar {
        id: infoBar
        Layout.fillWidth: true
        visible: false
        closable: true
    }

    // 标题
    SettingCard {
        Layout.fillWidth: true
        title: qsTr("标题")
        description: qsTr("文本的显示名称")
        icon.name: "ic_fluent_text_font_20_regular"

        TextField {
            id: titleField
            Layout.preferredWidth: 260
            placeholderText: qsTr("请输入文本标题")
        }
    }

    // 内容
    SettingCard {
        Layout.fillWidth: true
        title: qsTr("内容")
        description: qsTr("支持从文件导入或手动输入")
        icon.name: "ic_fluent_document_text_20_regular"

        Button {
            text: qsTr("从文件导入")
            icon.name: "ic_fluent_folder_open_20_regular"
            onClicked: {
                if (appBridge) appBridge.openTextFileDialog();
            }
        }
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
        Layout.topMargin: 8
        typography: Typography.Subtitle
        text: qsTr("上传目标")
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("本地文本库")
        description: qsTr("保存到本地，可离线使用")
        icon.name: "ic_fluent_folder_20_regular"

        CheckBox {
            id: localCheckBox
            checked: true
            onCheckedChanged: uploadPage.toLocal = checked
        }
    }

    SettingCard {
        Layout.fillWidth: true
        title: qsTr("云端（仅管理员）")
        description: qsTr("上传到服务端，需登录且具有管理员权限")
        icon.name: "ic_fluent_cloud_20_regular"

        CheckBox {
            id: cloudCheckBox
            enabled: appBridge ? appBridge.loggedin : false
            onCheckedChanged: uploadPage.toCloud = checked
        }
    }

    // 上传进度
    ProgressBar {
        Layout.fillWidth: true
        visible: uploadPage.uploading
        indeterminate: true
    }

    // 按钮区
    Item {
        Layout.fillHeight: true
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Item { Layout.fillWidth: true }

        Button {
            text: qsTr("取消")
            onClicked: clearForm()
        }

        Button {
            id: uploadBtn
            text: qsTr("上传")
            highlighted: true
            enabled: !uploadPage.uploading
            onClicked: {
                var title = titleField.text.trim();
                var content = contentArea.text.trim();
                if (!title) {
                    showInfo(Severity.Error, qsTr("验证失败"), qsTr("请输入标题"));
                    return;
                }
                if (!content) {
                    showInfo(Severity.Error, qsTr("验证失败"), qsTr("请输入内容"));
                    return;
                }
                if (!uploadPage.toLocal && !uploadPage.toCloud) {
                    showInfo(Severity.Error, qsTr("验证失败"), qsTr("请至少选择一个上传目标"));
                    return;
                }
                infoBar.visible = false;
                uploadPage.uploading = true;
                if (appBridge)
                    appBridge.uploadText(title, content, "custom", uploadPage.toLocal, uploadPage.toCloud);
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onUploadResult(success, message, textId) {
            uploadPage.uploading = false;
            if (success) {
                clearForm();
                showInfo(Severity.Success, qsTr("上传成功"), message || qsTr("文本已成功上传"));
            } else {
                showInfo(Severity.Error, qsTr("上传失败"), message);
            }
        }
        function onLoggedinChanged() {
            if (appBridge && !appBridge.loggedin) {
                uploadPage.toCloud = false;
                cloudCheckBox.checked = false;
            }
        }
        function onTextFileLoaded(content) {
            if (content) {
                contentArea.text = content;
                showInfo(Severity.Info, qsTr("文件已导入"), qsTr("文本内容已填充，请检查并上传"));
            } else {
                showInfo(Severity.Error, qsTr("导入失败"), qsTr("无法读取文件内容"));
            }
        }
    }
}
