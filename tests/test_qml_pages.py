from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_main_window_includes_local_articles_navigation_item():
    main_qml = PROJECT_ROOT / "src/qml/Main.qml"

    source = main_qml.read_text(encoding="utf-8")

    assert 'title: qsTr("本地文库")' in source
    assert 'page: Qt.resolvedUrl("pages/LocalArticlesPage.qml")' in source


def test_main_window_includes_trainer_navigation_item():
    main_qml = PROJECT_ROOT / "src/qml/Main.qml"

    source = main_qml.read_text(encoding="utf-8")

    assert 'title: qsTr("练单器")' in source
    assert 'page: Qt.resolvedUrl("pages/TrainerPage.qml")' in source


def test_trainer_page_uses_expected_bridge_contract():
    page_qml = PROJECT_ROOT / "src/qml/pages/TrainerPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "property bool active: false" in source
    assert "appBridge.trainerLoading" in source
    assert "appBridge.loadTrainers()" in source
    assert "appBridge.loadTrainerSegment(" in source
    assert "onTrainersLoaded" in source
    assert "onTrainersLoadFailed" in source
    assert "onTrainerSegmentLoaded" in source
    assert "onTrainerSegmentLoadFailed" in source
    assert "currentIndex: 1 // 默认“重打”" in source
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))' in source
    )
    assert "Qt.callLater(function() {" in source


def test_local_articles_page_uses_expected_bridge_contract():
    page_qml = PROJECT_ROOT / "src/qml/pages/LocalArticlesPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "property bool active: false" in source
    assert "appBridge.localArticleLoading" in source
    assert "appBridge.loadLocalArticles()" in source
    assert "appBridge.loadLocalArticleSegment(" in source
    assert "onLocalArticlesLoaded" in source
    assert "onLocalArticlesLoadFailed" in source
    assert "onLocalArticleSegmentLoaded" in source
    assert "onLocalArticleSegmentLoadFailed" in source
    assert "onLocalArticleLoadingChanged" in source
    assert "currentIndex: 1 // 默认“重打”" in source
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))' in source
    )
    assert "Qt.callLater(function() {" in source


def test_local_articles_page_accepts_modified_timestamp_alias():
    page_qml = PROJECT_ROOT / "src/qml/pages/LocalArticlesPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "article.modifiedTimestamp" in source


def test_typing_page_handles_local_article_segment_load_failure():
    page_qml = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "onLocalArticleSegmentLoadFailed" in source
    assert "upperPane.text = message" in source


def test_slice_config_dialog_defaults_on_fail_action_to_retype():
    dialog_qml = PROJECT_ROOT / "src/qml/typing/SliceConfigDialog.qml"

    source = dialog_qml.read_text(encoding="utf-8")

    assert "onFailActionCombo.currentIndex = 1; // 默认“重打”，避免默认乱序" in source


def test_typing_page_renders_ziti_hint_from_bridge():
    page_qml = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "appBridge.zitiEnabled" in source
    assert "appBridge.getZitiHint(" in source
    assert "zitiHintText" in source


def test_settings_page_exposes_ziti_controls():
    page_qml = PROJECT_ROOT / "src/qml/pages/SettingsPage.qml"

    source = page_qml.read_text(encoding="utf-8")

    assert "appBridge.loadZitiSchemes()" in source
    assert "appBridge.loadZitiScheme(" in source
    assert "appBridge.setZitiEnabled(" in source
    assert "onZitiSchemesLoaded" in source
