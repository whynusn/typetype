import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

Dialog {
    id: root
    modal: true
    title: qsTr("发现历史进度")
    width: 380

    property var progressInfo: ({})
    signal startFresh()
    signal restoreAccepted()
    signal restoreRejected()

    function advanceModeText(mode) {
        if (mode === "random") return qsTr("随机下一段");
        return qsTr("顺序下一段");
    }

    function cleanTitle(title) {
        return title.replace(/（乱序）$/, "").replace(/\(乱序\)$/, "");
    }

    function onFailText(action) {
        if (action === "retype") return qsTr("重打");
        if (action === "shuffle") return qsTr("乱序重打");
        return qsTr("无动作");
    }

    contentItem: ColumnLayout {
        spacing: 12

        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            Layout.fillWidth: true

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("文本")
            }
            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                text: root.cleanTitle(root.progressInfo.saved_title || "")
                elide: Text.ElideRight
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("分段进度")
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    typography: Typography.Caption
                    text: qsTr("第 %1 / %2 段").arg(root.progressInfo.saved_slice || 0).arg(root.progressInfo.saved_total || 0)
                }
                ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, root.progressInfo.saved_total || 0)
                    value: root.progressInfo.saved_slice || 0
                }
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("每段字数")
            }
            Text {
                typography: Typography.Caption
                text: root.progressInfo.slice_size || 0
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("推进模式")
            }
            Text {
                typography: Typography.Caption
                text: root.advanceModeText(root.progressInfo.advance_mode || "sequential")
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("上次访问")
            }
            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                text: root.progressInfo.last_accessed || "-"
                elide: Text.ElideRight
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            Layout.fillWidth: true

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("本段达标")
            }
            Text {
                typography: Typography.Caption
                text: (root.progressInfo.saved_pass_count_min || 1) > 1
                    ? qsTr("%1 / %2 次").arg(root.progressInfo.current_pass_count || 0).arg(root.progressInfo.saved_pass_count_min || 1)
                    : qsTr("需达标 1 次")
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("达标要求")
            }
            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                text: {
                    var parts = [];
                    if ((root.progressInfo.saved_ks || 0) > 0)
                        parts.push(qsTr("击键≥%1").arg(root.progressInfo.saved_ks.toFixed(1)));
                    if ((root.progressInfo.saved_spd || 0) > 0)
                        parts.push(qsTr("速度≥%1").arg(root.progressInfo.saved_spd));
                    if ((root.progressInfo.saved_acc || 0) > 0)
                        parts.push(qsTr("准确≥%1%").arg(root.progressInfo.saved_acc));
                    return parts.length > 0 ? parts.join("  ") : qsTr("无");
                }
            }

            Text {
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: qsTr("失败处理")
            }
            Text {
                typography: Typography.Caption
                text: root.onFailText(root.progressInfo.saved_onfail || "retype")
            }
        }
    }

    footer: DialogButtonBox {
        Button {
            text: qsTr("取消")
            QQC.DialogButtonBox.buttonRole: QQC.DialogButtonBox.RejectRole
        }
        Button {
            text: qsTr("重新开始")
            onClicked: {
                root.close();
                root.startFresh();
            }
        }
        Button {
            text: qsTr("继续上次进度")
            QQC.DialogButtonBox.buttonRole: QQC.DialogButtonBox.AcceptRole
        }

        onAccepted: {
            root.close();
            root.restoreAccepted();
        }
        onRejected: {
            root.close();
            root.restoreRejected();
        }
    }
}
