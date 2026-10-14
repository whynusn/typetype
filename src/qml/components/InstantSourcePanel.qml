import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

/**
 * 即时源面板公共骨架（晴发文 / AI 推荐共用）。
 *
 * 承载居中 560 布局、图标/标题/描述、错误行与主操作行；
 * 各来源特有内容（登录状态行、配置摘要卡、未配置引导等）经默认插槽注入。
 * 对外契约：loadRequested 信号 + errorText 属性；配置入口统一跳转设置页。
 */
Frame {
    id: root

    // ---- 输出 ----
    signal loadRequested()  // 主操作触发（由父级接入对应 appBridge 载文入口）

    // 上次加载失败信息（父级在 *LoadFailed 时写入，再次发起时清空）。
    // 载文在 TypingPage 完成，回到本面板时用户需要能看到失败原因。
    property string errorText: ""

    // ---- 骨架文案 ----
    property string icon: ""
    property string title: ""
    property string description: ""

    // ---- 主操作 ----
    // loading 驱动 BusyIndicator 与按钮禁用；actionEnabled 供来源附加前置条件
    // （如 AI 需已配置 API Key）；actionVisible 供来源整体隐藏主操作行
    property bool loading: false
    property string actionText: ""
    property bool actionEnabled: true
    property bool actionVisible: true

    // 来源特有内容插槽（登录状态行 / 配置摘要卡 / 未配置引导）
    default property alias panelContent: contentSlot.data

    // 跳转设置页（相对 URL 以本文件位置解析）
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
            icon: root.icon
            color: Theme.currentTheme.colors.primaryColor
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Subtitle
            color: Theme.currentTheme.colors.textColor
            text: root.title
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: root.description
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }

        // ---- 来源特有内容插槽区 ----
        ColumnLayout {
            id: contentSlot
            Layout.fillWidth: true
            spacing: 12
        }

        // ---- 上次失败反馈 ----
        Text {
            Layout.fillWidth: true
            visible: root.errorText.length > 0
            text: root.errorText
            typography: Typography.Caption
            color: Theme.currentTheme.colors.systemCriticalColor
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }

        // ---- 主操作 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: 8
            visible: root.actionVisible

            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                running: root.loading
                visible: running
            }

            Button {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                text: root.actionText
                highlighted: true
                enabled: root.actionEnabled && !root.loading
                onClicked: root.loadRequested()
            }
        }
    }
}
