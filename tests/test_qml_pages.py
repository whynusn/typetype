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


def test_main_window_has_unified_text_load_hub():
    main_qml = QML_DIR / "Main.qml"
    source = main_qml.read_text(encoding="utf-8")
    assert 'title: qsTr("载文")' in source
    assert 'page: Qt.resolvedUrl("pages/TextLoadHubPage.qml")' in source
    # 旧入口已被移除
    assert 'title: qsTr("极速杯载文")' not in source
    assert 'title: qsTr("本地文库")' not in source
    assert 'title: qsTr("自定义载文")' not in source
    assert 'title: qsTr("练单器")' not in source


def test_text_load_hub_uses_expected_bridge_contract():
    page_qml = QML_DIR / "pages/TextLoadHubPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "property bool active: false" in source
    assert "TextSourceListPanel" in source
    assert "SliceCriteriaPanel" in source
    assert "SliceSettingsPanel" in source

    # 列表加载
    assert "loadTextList" in refs and "loadTextList" in BRIDGE_SLOTS
    assert "loadLocalArticles" in refs and "loadLocalArticles" in BRIDGE_SLOTS
    assert "loadTrainers" in refs and "loadTrainers" in BRIDGE_SLOTS
    assert "loadCatalog" in refs and "loadCatalog" in BRIDGE_SLOTS

    # 内容/分段加载
    assert "getTextContentById" in refs and "getTextContentById" in BRIDGE_SLOTS
    assert "loadLibraryText" in refs and "loadLibraryText" in BRIDGE_SLOTS
    assert (
        "loadLocalArticleSegment" in refs and "loadLocalArticleSegment" in BRIDGE_SLOTS
    )
    assert "loadTrainerSegment" in refs and "loadTrainerSegment" in BRIDGE_SLOTS
    assert "loadFullText" in refs and "loadFullText" in BRIDGE_SLOTS
    assert "setupSliceMode" in refs and "setupSliceMode" in BRIDGE_SLOTS

    # 状态属性
    assert "textListLoading" in refs and "textListLoading" in BRIDGE_PROPERTIES
    assert "localArticleLoading" in refs and "localArticleLoading" in BRIDGE_PROPERTIES
    assert "trainerLoading" in refs and "trainerLoading" in BRIDGE_PROPERTIES

    # 信号
    for signal in (
        "textListLoaded",
        "textListLoadFailed",
        "textContentLoaded",
        "catalogLoaded",
        "catalogLoadFailed",
        "localArticlesLoaded",
        "localArticlesLoadFailed",
        "localArticleSegmentLoaded",
        "localArticleSegmentLoadFailed",
        "localArticleDeleted",
        "localArticleRenamed",
        "trainersLoaded",
        "trainersLoadFailed",
        "trainerSegmentLoaded",
        "trainerSegmentLoadFailed",
    ):
        assert signal in BRIDGE_SIGNALS

    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))' in source
    )


def test_text_leaderboard_page_uses_expected_bridge_contract():
    page_qml = QML_DIR / "pages/TextLeaderboardPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "property bool active: false" in source
    assert "TextSourceListPanel" in source
    assert (
        "loadLeaderboardByTextId" in refs and "loadLeaderboardByTextId" in BRIDGE_SLOTS
    )
    assert "loadTextList" in refs and "loadTextList" in BRIDGE_SLOTS
    assert "loadCatalog" in refs and "loadCatalog" in BRIDGE_SLOTS
    assert "refreshCatalog" in refs and "refreshCatalog" in BRIDGE_SLOTS
    assert "leaderboardLoaded" in BRIDGE_SIGNALS
    assert "leaderboardLoadFailed" in BRIDGE_SIGNALS


def test_typing_page_opens_unified_text_load_hub():
    page_qml = QML_DIR / "pages/TypingPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TextLoadHubPage.qml"), { initialSource: "custom" })'
        in source
    )


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
