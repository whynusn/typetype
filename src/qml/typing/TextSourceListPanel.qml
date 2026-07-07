import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

/**
 * 通用文本/文章/词库列表面板。
 *
 * 特性：
 * - 标题 + 刷新按钮 + 可扩展头部插槽
 * - 实时搜索过滤
 * - 使用 RinUI ListViewDelegate 的统一列表项样式
 * - 暴露 currentItem，触发 itemClicked / refreshRequested 信号
 */
Frame {
    id: root

    // ---- 输入 ----
    property string title: qsTr("列表")
    property string icon: "ic_fluent_document_text_20_regular"
    property var sourceItems: []
    property bool loading: false
    property string emptyText: qsTr("暂无项目")
    property bool searchable: true
    default property alias extraHeaderItems: extraHeaderRow.data

    // ---- 输出 ----
    readonly property alias currentIndex: listView.currentIndex
    readonly property var currentItem: (currentIndex >= 0 && currentIndex < listModel.count)
                                       ? listModel.get(currentIndex)
                                       : null

    signal itemClicked(int originalIndex)
    signal refreshRequested()

    // ---- 内部 ----
    function _matches(item, text) {
        var haystack = (item.title || "") + " " + (item.subtitle || "")
        return haystack.toLowerCase().indexOf(text.toLowerCase()) !== -1
    }

    function rebuild() {
        listModel.clear()
        var filter = searchField.text.trim()
        for (var i = 0; i < sourceItems.length; i++) {
            var item = sourceItems[i]
            if (!searchable || !filter || _matches(item, filter)) {
                listModel.append({
                    originalIndex: i,
                    title: item.title || "",
                    subtitle: item.subtitle || "",
                    raw: item.raw
                })
            }
        }
        if (listModel.count > 0) {
            listView.currentIndex = 0
        } else {
            listView.currentIndex = -1
        }
    }

    onSourceItemsChanged: Qt.callLater(rebuild)

    Layout.fillHeight: true
    Layout.fillWidth: true
    Layout.minimumWidth: 220
    radius: 6
    hoverable: false
    padding: 8

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            spacing: 8

            IconWidget {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                icon: root.icon
                color: Theme.currentTheme.colors.primaryColor
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.BodyStrong
                text: root.title
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                running: root.loading
                visible: running
            }

            RowLayout {
                id: extraHeaderRow
                spacing: 4
            }

            ToolButton {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                icon.name: "ic_fluent_arrow_sync_20_regular"
                flat: true
                enabled: !root.loading
                onClicked: root.refreshRequested()
                ToolTip { text: qsTr("刷新"); visible: parent.hovered }
            }
        }

        TextField {
            id: searchField
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            visible: root.searchable
            placeholderText: qsTr("搜索...")
            onTextChanged: root.rebuild()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: ListModel { id: listModel }
            boundsBehavior: Flickable.StopAtBounds

            delegate: ListViewDelegate {
                width: listView.width
                highlighted: listView.currentIndex === index

                middleArea: [
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Body
                            text: model.title
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: model.subtitle
                            elide: Text.ElideRight
                            visible: model.subtitle.length > 0
                        }
                    }
                ]

                onClicked: {
                    listView.currentIndex = index
                    root.itemClicked(model.originalIndex)
                }
            }

            Text {
                anchors.centerIn: parent
                width: parent.width - 24
                typography: Typography.Body
                color: Theme.currentTheme.colors.textSecondaryColor
                text: root.loading ? qsTr("加载中...") : root.emptyText
                horizontalAlignment: Text.AlignHCenter
                visible: listModel.count === 0
                wrapMode: Text.WordWrap
            }
        }
    }
}
