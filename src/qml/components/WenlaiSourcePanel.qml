import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

/**
 * 晴发文即时源面板。
 *
 * 展示登录状态与加载配置摘要，提供「随机一篇」主操作。
 * 配置/登录入口统一跳转设置页；状态一律经 appBridge 读取（null 守卫）。
 */
Frame {
    id: root

    // ---- 输出 ----
    signal loadRequested()  // 「随机一篇」触发（由父级接入 appBridge.loadRandomWenlaiText）

    // 跳转设置页（相对 URL 以本文件位置解析，与 typing/SliceHelpers 惯例一致）
    function openSettings() {
        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("../pages/SettingsPage.qml"))
        }
    }

    Layout.fillWidth: true
    Layout.fillHeight: true
    radius: 6
    hoverable: false

    // ---- 内容（居中，最大宽度 560） ----
    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 32, 560)
        spacing: 12

        IconWidget {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            icon: "ic_fluent_book_20_regular"
            color: Theme.currentTheme.colors.primaryColor
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Subtitle
            color: Theme.currentTheme.colors.textColor
            text: qsTr("晴发文")
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: qsTr("每次从晴发文随机获取一篇文章，分段连载，即点即打。")
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }

        // ---- 登录状态行 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Body
                color: Theme.currentTheme.colors.textColor
                text: (appBridge && appBridge.wenlaiLoggedIn)
                      ? qsTr("已登录：%1").arg(appBridge.wenlaiCurrentUser)
                      : qsTr("未登录（部分书库受限）")
                elide: Text.ElideRight
            }

            Button {
                text: (appBridge && appBridge.wenlaiLoggedIn) ? qsTr("账号设置") : qsTr("去登录")
                flat: true
                onClicked: root.openSettings()
            }
        }

        // ---- 配置摘要卡 ----
        Frame {
            Layout.fillWidth: true
            radius: 6
            hoverable: false
            padding: 12

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("长度")
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        typography: Typography.Body
                        color: Theme.currentTheme.colors.textColor
                        text: (appBridge && appBridge.wenlaiLength > 0) ? appBridge.wenlaiLength : qsTr("默认")
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("难度")
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        typography: Typography.Body
                        color: Theme.currentTheme.colors.textColor
                        text: (appBridge && appBridge.wenlaiDifficultyLevel > 0) ? appBridge.wenlaiDifficultyLevel : qsTr("全部")
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("分类")
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        typography: Typography.Body
                        color: Theme.currentTheme.colors.textColor
                        text: (appBridge && appBridge.wenlaiCategory) ? appBridge.wenlaiCategory : qsTr("全部")
                        elide: Text.ElideRight
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: qsTr("分段模式")
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        typography: Typography.Body
                        color: Theme.currentTheme.colors.textColor
                        text: (appBridge && appBridge.wenlaiSegmentMode === "auto") ? qsTr("自动分段") : qsTr("手动分段")
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    Button {
                        text: qsTr("修改配置")
                        flat: true
                        onClicked: root.openSettings()
                    }
                }
            }
        }

        // ---- 主操作 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: 8

            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                running: appBridge ? appBridge.wenlaiLoading : false
                visible: running
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                text: qsTr("随机一篇")
                highlighted: true
                enabled: appBridge && !appBridge.wenlaiLoading
                onClicked: root.loadRequested()
            }
        }
    }
}
