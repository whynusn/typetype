import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import RinUI
import "../typing"

Item {
    id: localArticlesPage
    property bool active: false  // 由 NavigationView 注入

    property int selectedArticleIndex: -1
    property var selectedArticle: null
    property string errorMessage: ""
    property string statusMessage: ""
    property bool hasProgress: false
    readonly property var _navigationView: Window.window ? Window.window.navigationView : null

    // 分片模式开关（true=分片，false=全文）
    property bool sliceModeChecked: true

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

    function formatTimestamp(ts) {
        if (!ts || ts <= 0) return "-";
        var d = new Date(ts * 1000);
        return Qt.formatDateTime(d, "yyyy-MM-dd hh:mm");
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
        errorMessage = "";
        statusMessage = qsTr("已选择：") + articleTitle(selectedArticle);
        checkProgress();
    }

    function checkProgress() {
        if (selectedArticle && appBridge) {
            hasProgress = appBridge.hasSliceProgress(appBridge.getProgressKey("local_article", articleId(selectedArticle)), articleTitle(selectedArticle));
        } else {
            hasProgress = false;
        }
    }

    function continueLastProgress() {
        if (!appBridge || !selectedArticle) {
            errorMessage = qsTr("请选择一篇文章");
            return;
        }
        var idValue = articleId(selectedArticle);
        if (idValue === "" || idValue === null || idValue === undefined) {
            errorMessage = qsTr("文章缺少可加载的 ID");
            return;
        }

        var progressKey = appBridge.getProgressKey("local_article", idValue);
        var infoJson = appBridge.getSliceProgressInfo(progressKey, articleTitle(selectedArticle));
        if (!infoJson || infoJson.length === 0) {
            // 无进度，直接开始
            loadSelectedSegment();
            return;
        }

        progressRestoreDialog.progressInfo = JSON.parse(infoJson);
        progressRestoreDialog._articleId = idValue;
        progressRestoreDialog._articleTitle = articleTitle(selectedArticle);
        progressRestoreDialog.open();
    }

    function syncLocalArticles(articles) {
        selectedArticle = null;
        selectedArticleIndex = -1;
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
        // 非恢复流程：清除可能残留的待恢复进度
        appBridge.clearPendingRestore();

        var size = sliceSettingsPanel.sliceSize;
        var index = Math.max(1, Math.min(sliceSettingsPanel.startSlice, sliceSettingsPanel.totalSlices));
        var fullText = !localArticlesPage.sliceModeChecked;

        if (fullText) {
            size = articleCharCount(selectedArticle);
            index = 1;
        }

        errorMessage = "";
        statusMessage = fullText ? qsTr("正在载入全文...") : qsTr("正在打开第 %1 段...").arg(index);

        // 自动推进参数通过 SliceCriteriaPanel 组件设置
        if (appBridge) {
            var criteriaOn = sliceCriteriaPanel.conditionChecked;
            appBridge.setSliceCriteria(
                criteriaOn ? sliceCriteriaPanel.keyStrokeMinValue : 0,
                criteriaOn ? sliceCriteriaPanel.speedMinValue : 0,
                criteriaOn ? sliceCriteriaPanel.accuracyMinValue : 0,
                criteriaOn ? sliceCriteriaPanel.passCountMinValue : 1,
                criteriaOn ? sliceCriteriaPanel.onFailActionValue : "none",
                sliceCriteriaPanel.advanceModeValue,
                sliceSettingsPanel.fullShuffleChecked,
                sliceCriteriaPanel.autoDecreaseEnabled,
                sliceCriteriaPanel.keyStrokeDecreaseValue,
                sliceCriteriaPanel.speedDecreaseValue,
                sliceCriteriaPanel.accuracyDecreaseValue
            );
        }

        if (Window.window && Window.window.navigationView) {
            Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
        }

        Qt.callLater(function () {
            if (appBridge) {
                if (fullText) {
                    appBridge.loadLocalArticleSegment(idValue, 1, size);
                } else {
                    appBridge.loadLocalArticleSegment(idValue, index, size);
                }
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

            ToolButton {
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_left_20_regular"
                flat: true
                onClicked: {
                    if (Window.window && Window.window.navigationView)
                        Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"));
                }
                ToolTip { text: qsTr("返回"); visible: parent.hovered }
            }

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
                icon.name: "ic_fluent_add_20_regular"
                flat: true
                onClicked: {
                    if (Window.window && Window.window.navigationView) {
                        Window.window.navigationView.push(Qt.resolvedUrl("UploadTextPage.qml"));
                    }
                }
                ToolTip {
                    text: qsTr("上传文本")
                    visible: parent.hovered

                }
            }

            ToolButton {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                icon.name: "ic_fluent_arrow_sync_20_regular"
                enabled: !(appBridge && appBridge.localArticleLoading)
                flat: true
                onClicked: refreshArticles()
                ToolTip {
                    text: qsTr("刷新")
                    visible: parent.hovered

                }
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

                        QQC.ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            width: articleListView.width
                            height: 58
                            radius: 6
                            color: index === selectedArticleIndex ? Theme.currentTheme.colors.subtleSecondaryColor : "transparent"

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
                                    color: index === selectedArticleIndex ? Theme.currentTheme.colors.primaryColor : Theme.currentTheme.colors.textSecondaryColor
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

                Flickable {
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
                        width: parent.width
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

                            ToolButton {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                icon.name: "ic_fluent_rename_20_regular"
                                enabled: selectedArticle !== null && !selectedArticle.isBundled
                                onClicked: renameDialog.open()
                                ToolTip {
                                    text: qsTr("重命名")
                                    visible: parent.hovered
                
                                }
                            }

                            ToolButton {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                icon.name: "ic_fluent_delete_20_regular"
                                enabled: selectedArticle !== null && !selectedArticle.isBundled
                                onClicked: deleteConfirmDialog.open()
                                ToolTip {
                                    text: qsTr("删除")
                                    visible: parent.hovered
                
                                }
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
                                text: selectedArticle ? formatTimestamp(articleUpdatedAt(selectedArticle)) : "-"
                                elide: Text.ElideRight
                            }
                        }

                        // --- 分片设置（复用组件）---
                        SliceSettingsPanel {
                            id: sliceSettingsPanel
                            Layout.fillWidth: true
                            sliceModeChecked: localArticlesPage.sliceModeChecked
                            contentLength: selectedArticle ? articleCharCount(selectedArticle) : 0
                            sliceSize: 100
                            startSlice: 1
                            onSliceModeCheckedChanged: localArticlesPage.sliceModeChecked = sliceModeChecked
                        }

                        // --- 达标条件（复用组件）---
                        SliceCriteriaPanel {
                            id: sliceCriteriaPanel
                            Layout.fillWidth: true
                            visible: localArticlesPage.sliceModeChecked
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 24
                            typography: Typography.Caption
                            color: errorMessage.length > 0 ? Theme.currentTheme.colors.systemCriticalColor : Theme.currentTheme.colors.textSecondaryColor
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

                            Button {
                                Layout.preferredHeight: 34
                                text: qsTr("继续上次进度")
                                visible: hasProgress
                                enabled: selectedArticle !== null && !(appBridge && appBridge.localArticleLoading)
                                onClicked: continueLastProgress()
                            }
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
            statusMessage = articleListModel.count > 0 ? qsTr("已加载 %1 篇本地文章").arg(articleListModel.count) : qsTr("未找到本地文章");
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

        function onLocalArticleDeleted(success, message) {
            if (success) {
                statusMessage = message;
                errorMessage = "";
                refreshArticles();
            } else {
                errorMessage = message;
            }
        }

        function onLocalArticleRenamed(success, message) {
            if (success) {
                statusMessage = message;
                errorMessage = "";
                refreshArticles();
            } else {
                errorMessage = message;
            }
        }
    }

    Dialog {
        id: deleteConfirmDialog
        title: qsTr("确认删除")
        modal: true
        anchors.centerIn: QQC.Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string targetArticleId: ""
        property string targetArticleTitle: ""

        Text {
            text: qsTr("确定要删除文章「%1」吗？此操作不可撤销。").arg(deleteConfirmDialog.targetArticleTitle)
        }

        onOpened: {
            targetArticleId = selectedArticle ? articleId(selectedArticle) : "";
            targetArticleTitle = selectedArticle ? articleTitle(selectedArticle) : "";
        }

        onAccepted: {
            if (appBridge && targetArticleId) {
                appBridge.deleteLocalArticle(targetArticleId);
            }
        }
    }

    Dialog {
        id: renameDialog
        title: qsTr("重命名")
        modal: true
        anchors.centerIn: QQC.Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string targetArticleId: ""

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: qsTr("新名称：")
            }
            TextField {
                id: renameTextField
                Layout.fillWidth: true
                selectByMouse: true
            }
        }

        onOpened: {
            targetArticleId = selectedArticle ? articleId(selectedArticle) : "";
            renameTextField.text = selectedArticle ? articleTitle(selectedArticle) : "";
            renameTextField.selectAll();
            renameTextField.forceActiveFocus();
        }

        onAccepted: {
            var newName = renameTextField.text.trim();
            if (newName && appBridge && targetArticleId) {
                appBridge.renameLocalArticle(targetArticleId, newName);
            }
        }
    }

    SliceProgressRestoreDialog {
        id: progressRestoreDialog
        property string _articleId: ""
        property string _articleTitle: ""
        onRestoreAccepted: {
            appBridge.prepareSliceProgressRestore(appBridge.getProgressKey("local_article", _articleId), _articleTitle);
            var settings = JSON.parse(appBridge.getRestoredSliceSettings());
            SliceHelpers.startWithCriteria(
                appBridge, localArticlesPage._navigationView,
                sliceSettingsPanel, sliceCriteriaPanel, settings,
                function(size) { appBridge.loadLocalArticleSegment(_articleId, 1, size); }
            );
        }
        onStartFresh: {
            appBridge.applySliceProgressRestore(appBridge.getProgressKey("local_article", _articleId), false, _articleTitle);
            localArticlesPage.loadSelectedSegment();
        }
    }
}
