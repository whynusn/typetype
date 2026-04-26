import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI

Item {
    id: localArticlesPage
    property bool active: false  // 由 NavigationView 注入

    property int selectedArticleIndex: -1
    property var selectedArticle: null
    property string errorMessage: ""
    property string statusMessage: ""

    function articleId(article) {
        if (!article)
            return "";
        if (article.articleId !== undefined)
            return article.articleId;
        if (article.article_id !== undefined)
            return article.article_id;
        if (article.id !== undefined)
            return article.id;
        if (article.client_id !== undefined)
            return article.client_id;
        return "";
    }

    function articleTitle(article) {
        if (!article)
            return qsTr("未选择文章");
        return article.title || article.name || article.filename || qsTr("未命名文章");
    }

    function articleCharCount(article) {
        if (!article)
            return 0;
        return article.charCount || article.char_count || article.contentLength || article.content_length || article.length || 0;
    }

    function articleUpdatedAt(article) {
        if (!article)
            return "";
        return article.updatedAt || article.updated_at || article.modifiedTimestamp || article.modified_timestamp || article.createdAt || article.created_at || "";
    }

    function segmentSizeValue() {
        return Math.max(1, segmentSizeSpin.value);
    }

    function segmentCount() {
        var total = articleCharCount(selectedArticle);
        if (total <= 0)
            return 1;
        return Math.max(1, Math.ceil(total / segmentSizeValue()));
    }

    function clampSegmentIndex() {
        segmentIndexSpin.to = Math.max(1, segmentCount());
        if (segmentIndexSpin.value > segmentIndexSpin.to)
            segmentIndexSpin.value = segmentIndexSpin.to;
        if (segmentIndexSpin.value < 1)
            segmentIndexSpin.value = 1;
    }

    function selectArticle(index) {
        if (index < 0 || index >= articleListModel.count) {
            selectedArticleIndex = -1;
            selectedArticle = null;
            return;
        }
        selectedArticleIndex = index;
        selectedArticle = articleListModel.get(index);
        articleListView.currentIndex = index;
        clampSegmentIndex();
        errorMessage = "";
        statusMessage = qsTr("已选择：") + articleTitle(selectedArticle);
    }

    function syncLocalArticles(articles) {
        articleListModel.clear();
        if (articles) {
            for (var i = 0; i < articles.length; i++) {
                articleListModel.append(articles[i]);
            }
        }
        if (articleListModel.count > 0)
            selectArticle(0);
        else
            selectArticle(-1);
    }

    function refreshArticles() {
        if (!appBridge)
            return;
        errorMessage = "";
        statusMessage = qsTr("正在扫描本地文库...");
        appBridge.loadLocalArticles();
    }

    function loadSelectedSegment() {
        if (!appBridge || !selectedArticle) {
            errorMessage = qsTr("请选择一篇文章");
            return;
        }
        var idValue = articleId(selectedArticle);
        if (idValue === "" || idValue === null || idValue === undefined) {
            errorMessage = qsTr("文章缺少可加载的 ID");
            return;
        }
        var size = segmentSizeValue();
        var index = Math.max(1, Math.min(segmentIndexSpin.value, segmentCount()));
        errorMessage = "";
        statusMessage = qsTr("正在打开第 %1 段...").arg(index);
        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
        }
        Qt.callLater(function() {
            if (appBridge) {
                appBridge.loadLocalArticleSegment(idValue, index, size);
            }
        });
    }

    onActiveChanged: {
        if (active && appBridge) {
            refreshArticles();
        }
    }

    ListModel {
        id: articleListModel
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Title
                text: qsTr("本地文库")
                elide: Text.ElideRight
            }

            Text {
                Layout.preferredWidth: 160
                typography: Typography.Caption
                color: Theme.currentTheme.colors.textSecondaryColor
                text: appBridge && appBridge.localArticleLoading ? qsTr("扫描中...") : qsTr("%1 篇文章").arg(articleListModel.count)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }

            BusyIndicator {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                running: appBridge ? appBridge.localArticleLoading : false
                visible: running
            }

            ToolButton {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !(appBridge && appBridge.localArticleLoading)
                flat: true
                onClicked: refreshArticles()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.currentTheme.colors.cardBorderColor
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Frame {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                radius: 6
                hoverable: false
                padding: 8

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        spacing: 6

                        IconWidget {
                            Layout.preferredWidth: 16
                            Layout.preferredHeight: 16
                            icon: "ic_fluent_document_text_20_regular"
                            color: Theme.currentTheme.colors.primaryColor
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: qsTr("文章")
                            elide: Text.ElideRight
                        }
                    }

                    ListView {
                        id: articleListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: articleListModel
                        currentIndex: selectedArticleIndex

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            width: articleListView.width
                            height: 58
                            radius: 6
                            color: index === selectedArticleIndex
                                ? Theme.currentTheme.colors.subtleSecondaryColor
                                : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectArticle(index)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                IconWidget {
                                    Layout.preferredWidth: 18
                                    Layout.preferredHeight: 18
                                    icon: "ic_fluent_document_text_20_regular"
                                    color: index === selectedArticleIndex
                                        ? Theme.currentTheme.colors.primaryColor
                                        : Theme.currentTheme.colors.textSecondaryColor
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Body
                                        text: articleTitle(model)
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        typography: Typography.Caption
                                        color: Theme.currentTheme.colors.textSecondaryColor
                                        text: qsTr("%1 字").arg(articleCharCount(model))
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 24
                            typography: Typography.Body
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: appBridge && appBridge.localArticleLoading ? qsTr("正在扫描...") : qsTr("暂无本地文章")
                            horizontalAlignment: Text.AlignHCenter
                            visible: articleListModel.count === 0
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Frame {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 6
                hoverable: false
                padding: 12

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        spacing: 8

                        IconWidget {
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            icon: "ic_fluent_open_20_regular"
                            color: Theme.currentTheme.colors.primaryColor
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.BodyStrong
                            text: articleTitle(selectedArticle)
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.currentTheme.colors.cardBorderColor
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 12
                        rowSpacing: 8

                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("文章 ID")
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            text: selectedArticle ? String(articleId(selectedArticle)) : "-"
                            elide: Text.ElideRight
                        }

                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("字数")
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            text: selectedArticle ? qsTr("%1 字").arg(articleCharCount(selectedArticle)) : "-"
                            elide: Text.ElideRight
                        }

                        Text {
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("更新时间")
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            text: selectedArticle ? (articleUpdatedAt(selectedArticle) || "-") : "-"
                            elide: Text.ElideRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        spacing: 8

                        Text {
                            Layout.preferredWidth: 72
                            typography: Typography.Body
                            text: qsTr("每段字数")
                        }

                        SpinBox {
                            id: segmentSizeSpin
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 34
                            from: 1
                            to: 99999
                            value: 500
                            editable: true
                            stepSize: 50
                            onValueChanged: clampSegmentIndex()
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("共 %1 段").arg(segmentCount())
                            elide: Text.ElideRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        spacing: 8

                        Text {
                            Layout.preferredWidth: 72
                            typography: Typography.Body
                            text: qsTr("段落序号")
                        }

                        SpinBox {
                            id: segmentIndexSpin
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 34
                            from: 1
                            to: 1
                            value: 1
                            editable: true
                        }

                        Text {
                            Layout.fillWidth: true
                            typography: Typography.Caption
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: qsTr("范围 1-%1").arg(segmentIndexSpin.to)
                            elide: Text.ElideRight
                        }
                    }

                    Item {
                        Layout.fillHeight: true
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        typography: Typography.Caption
                        color: errorMessage.length > 0
                            ? Theme.currentTheme.colors.systemCriticalColor
                            : Theme.currentTheme.colors.textSecondaryColor
                        text: errorMessage.length > 0 ? errorMessage : statusMessage
                        elide: Text.ElideRight
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        spacing: 8

                        Item {
                            Layout.fillWidth: true
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("刷新")
                            enabled: !(appBridge && appBridge.localArticleLoading)
                            onClicked: refreshArticles()
                        }

                        Button {
                            Layout.preferredHeight: 34
                            text: qsTr("载入跟打")
                            highlighted: true
                            enabled: selectedArticle !== null && !(appBridge && appBridge.localArticleLoading)
                            onClicked: loadSelectedSegment()
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        enabled: appBridge !== null

        function onLocalArticlesLoaded(articles) {
            syncLocalArticles(articles);
            statusMessage = articleListModel.count > 0
                ? qsTr("已加载 %1 篇本地文章").arg(articleListModel.count)
                : qsTr("未找到本地文章");
            errorMessage = "";
        }

        function onLocalArticlesLoadFailed(message) {
            errorMessage = message;
            statusMessage = "";
        }

        function onLocalArticleSegmentLoaded(segment) {
            var title = segment && segment.title ? segment.title : articleTitle(selectedArticle);
            statusMessage = qsTr("已载入：") + title;
            errorMessage = "";
        }

        function onLocalArticleSegmentLoadFailed(message) {
            errorMessage = message;
        }

        function onLocalArticleLoadingChanged() {
            if (appBridge && appBridge.localArticleLoading) {
                statusMessage = qsTr("正在处理本地文章...");
            }
        }
    }
}
