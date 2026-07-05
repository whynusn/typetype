"""QML page Bridge API introspection tests."""

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = PROJECT_ROOT / "src/backend/presentation/bridge.py"
QML_DIR = PROJECT_ROOT / "src/qml"

ALLOWLIST = {"objectName", "destroyed", "parent"}


def _parse_bridge_api():
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    signals = set()
    slots = set()
    properties = set()
    lines = source.split("\n")
    for m in re.finditer(r"^\s+(\w+)\s*=\s*Signal\(", source, re.MULTILINE):
        signals.add(m.group(1))
    for i, line in enumerate(lines):
        if line.strip().startswith("@Slot"):
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r"\s+def\s+(\w+)", lines[j])
                if m:
                    slots.add(m.group(1))
                    break
    for i, line in enumerate(lines):
        if line.strip().startswith("@Property"):
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r"\s+def\s+(\w+)", lines[j])
                if m:
                    properties.add(m.group(1))
                    break
    return slots, properties, signals


BRIDGE_SLOTS, BRIDGE_PROPERTIES, BRIDGE_SIGNALS = _parse_bridge_api()


def _get_qml_refs(source):
    refs = set()
    for m in re.finditer(r"appBridge\.(\w+)", source):
        refs.add(m.group(1))
    return refs


def test_main_window_includes_navigation_items():
    main_qml = QML_DIR / "Main.qml"
    source = main_qml.read_text(encoding="utf-8")
    assert 'title: qsTr("极速杯载文")' in source
    assert 'page: Qt.resolvedUrl("pages/JisuBeiPage.qml")' in source
    assert 'title: qsTr("本地文库")' in source
    assert 'page: Qt.resolvedUrl("pages/LocalArticlesPage.qml")' in source
    assert 'title: qsTr("自定义载文")' in source
    assert 'page: Qt.resolvedUrl("pages/CustomLoadTextPage.qml")' in source


def test_main_window_includes_trainer_navigation_item():
    main_qml = QML_DIR / "Main.qml"
    source = main_qml.read_text(encoding="utf-8")
    assert 'title: qsTr("练单器")' in source
    assert 'page: Qt.resolvedUrl("pages/TrainerPage.qml")' in source


def test_trainer_page_uses_expected_bridge_contract():
    page_qml = QML_DIR / "pages/TrainerPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "property bool active: false" in source
    assert "trainerLoading" in refs and "trainerLoading" in BRIDGE_PROPERTIES
    assert "loadTrainers" in refs and "loadTrainers" in BRIDGE_SLOTS
    assert "loadTrainerSegment" in refs and "loadTrainerSegment" in BRIDGE_SLOTS
    assert "trainersLoaded" in BRIDGE_SIGNALS
    assert "trainersLoadFailed" in BRIDGE_SIGNALS
    assert "trainerSegmentLoaded" in BRIDGE_SIGNALS
    assert "trainerSegmentLoadFailed" in BRIDGE_SIGNALS
    assert "SliceCriteriaPanel" in source
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))' in source
    )
    assert "Qt.callLater(function () {" in source


def test_local_articles_page_uses_expected_bridge_contract():
    page_qml = QML_DIR / "pages/LocalArticlesPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "property bool active: false" in source
    assert "localArticleLoading" in refs and "localArticleLoading" in BRIDGE_PROPERTIES
    assert "loadLocalArticles" in refs and "loadLocalArticles" in BRIDGE_SLOTS
    assert (
        "loadLocalArticleSegment" in refs and "loadLocalArticleSegment" in BRIDGE_SLOTS
    )
    assert "localArticlesLoaded" in BRIDGE_SIGNALS
    assert "localArticlesLoadFailed" in BRIDGE_SIGNALS
    assert "localArticleSegmentLoaded" in BRIDGE_SIGNALS
    assert "localArticleSegmentLoadFailed" in BRIDGE_SIGNALS
    assert "localArticleLoadingChanged" in BRIDGE_SIGNALS
    assert "SliceCriteriaPanel" in source
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))' in source
    )
    assert "Qt.callLater(function () {" in source


def test_local_articles_page_accepts_modified_timestamp_alias():
    page_qml = QML_DIR / "pages/LocalArticlesPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    assert "article.modifiedTimestamp" in source


def test_typing_page_handles_local_article_segment_load_failure():
    page_qml = QML_DIR / "pages/TypingPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "localArticleSegmentLoadFailed" in BRIDGE_SIGNALS
    assert "textReadOnly" in refs and "textReadOnly" in BRIDGE_PROPERTIES
    assert "setLowerPaneFocused" in refs and "setLowerPaneFocused" in BRIDGE_SLOTS
    assert "upperPane.text = message" in source


def test_typing_page_renders_ziti_hint_from_bridge():
    page_qml = QML_DIR / "pages/TypingPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "zitiEnabled" in refs and "zitiEnabled" in BRIDGE_PROPERTIES
    assert "getZitiHint" in refs and "getZitiHint" in BRIDGE_SLOTS
    assert "zitiHintText" in source


def test_settings_page_exposes_ziti_controls():
    page_qml = QML_DIR / "pages/SettingsPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "loadZitiSchemes" in refs and "loadZitiSchemes" in BRIDGE_SLOTS
    assert "loadZitiScheme" in refs and "loadZitiScheme" in BRIDGE_SLOTS
    assert "setZitiEnabled" in refs and "setZitiEnabled" in BRIDGE_SLOTS
    assert "zitiSchemesLoaded" in BRIDGE_SIGNALS


def test_all_appbridge_refs_are_valid_api():
    for qml_file in sorted(QML_DIR.rglob("*.qml")):
        source = qml_file.read_text(encoding="utf-8")
        refs = _get_qml_refs(source)
        if not refs:
            continue
        unknown = refs - BRIDGE_SLOTS - BRIDGE_PROPERTIES - ALLOWLIST
        assert not unknown, (
            f"{qml_file.relative_to(PROJECT_ROOT)}: "
            f"unknown appBridge references: {sorted(unknown)}"
        )
