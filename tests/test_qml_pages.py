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
    # 兼容 QML 的 appBridge.xxx 与 JS 分派模块的 bridge.xxx 两种写法
    for m in re.finditer(r"(?:appBridge|bridge)\.(\w+)", source):
        refs.add(m.group(1))
    return refs


def test_main_window_includes_unified_text_load_hub():
    main_qml = QML_DIR / "Main.qml"
    source = main_qml.read_text(encoding="utf-8")
    assert 'title: qsTr("载文")' in source
    assert 'page: Qt.resolvedUrl("pages/TextLoadHubPage.qml")' in source


def test_text_load_hub_uses_expected_bridge_contract():
    page_qml = QML_DIR / "pages/TextLoadHubPage.qml"
    qml_source = page_qml.read_text(encoding="utf-8")
    # 载文 trait 行为已下沉到 JS 分派模块，bridge 引用分布在 QML + JS 里
    js_behaviors = PROJECT_ROOT / "src/qml/helpers/TextSourceBehaviors.js"
    js_source = (
        js_behaviors.read_text(encoding="utf-8") if js_behaviors.exists() else ""
    )
    source = qml_source + js_source
    refs = _get_qml_refs(source)
    assert "property bool active: false" in qml_source
    assert "textListLoading" in refs and "textListLoading" in BRIDGE_PROPERTIES
    assert "localArticleLoading" in refs and "localArticleLoading" in BRIDGE_PROPERTIES
    assert "trainerLoading" in refs and "trainerLoading" in BRIDGE_PROPERTIES
    assert "loadTextList" in refs and "loadTextList" in BRIDGE_SLOTS
    assert "loadLocalArticles" in refs and "loadLocalArticles" in BRIDGE_SLOTS
    assert "loadCatalog" in BRIDGE_SLOTS
    assert "loadTrainers" in refs and "loadTrainers" in BRIDGE_SLOTS
    assert (
        "loadLocalArticleSegment" in refs and "loadLocalArticleSegment" in BRIDGE_SLOTS
    )
    assert "loadTrainerSegment" in refs and "loadTrainerSegment" in BRIDGE_SLOTS
    # OTT 源仓库联邦聚合 Slot
    assert "addRepo" in refs and "addRepo" in BRIDGE_SLOTS
    assert "removeRepo" in refs and "removeRepo" in BRIDGE_SLOTS
    assert "setRepoEnabled" in refs and "setRepoEnabled" in BRIDGE_SLOTS
    assert "refreshRepos" in refs and "refreshRepos" in BRIDGE_SLOTS
    assert "SliceCriteriaPanel" in qml_source
    assert "TextInfoCard" in qml_source
    assert (
        'Window.window.navigationView.push(Qt.resolvedUrl("TypingPage.qml"))'
        in qml_source
    )
    assert (
        "Qt.callLater(function() {" in source or "Qt.callLater(function () {" in source
    )


def test_text_load_hub_routes_text_sources_through_slice_launcher():
    page_qml = QML_DIR / "pages/TextLoadHubPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    js_behaviors = QML_DIR / "helpers/TextSourceBehaviors.js"
    js_source = js_behaviors.read_text(encoding="utf-8")

    assert 'launchKind: "segmented_source"' in js_source
    assert 'launchKind: "materialized_text"' in js_source

    assert "function buildLaunchRequest()" in source
    assert "function startTypingFromRequest(request, rp)" in source
    assert "function startMaterializedText(request, rp)" in source
    assert "function startSegmentedSource(request, rp)" in source
    assert "startTypingFromRequest(buildLaunchRequest()" in source
    assert "var fullText = !root.sliceModeChecked" in source

    custom_start = source.index("function startCustomTyping")
    custom_end = source.index("function canLoad", custom_start)
    custom_body = source[custom_start:custom_end]
    assert "textLoadPanel.sliceModeChecked" not in custom_body
    assert "textLoadPanel.sliceSize" not in custom_body
    assert "textLoadPanel.startSlice" not in custom_body


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


def test_text_load_hub_clears_pending_federated_flag_on_failure():
    """联邦 inline 加载失败或中途返回时，_pendingFederatedContent 必须清零。

    残留 flag 会把后续任意 textContentLoaded（如正常载文）误判成联邦内容
    启动打字。修复要求：独立联邦 Connections 里处理 textLoadFailed 清除
    flag，且 onActiveChanged 激活时（中途返回场景）也清除。
    """
    page_qml = QML_DIR / "pages/TextLoadHubPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    assert "textLoadFailed" in BRIDGE_SIGNALS
    assert "function onTextLoadFailed" in source
    # onActiveChanged 在 root 作用域内直接写 flag（无前缀）；联邦 Connections
    # 成功/失败 handler 在组件外部需 root. 前缀，失败分支同样清除 flag
    assert "_pendingFederatedContent = false" in source
    assert "root._pendingFederatedContent = null" in source
    # 失败 handler 必须在 flag 置位之后且与成功 handler 同处联邦 Connections，
    # 且失败分支内要有 flag 清除（onTextLoadFailed 函数体含 = null）
    failed_at = source.index("function onTextLoadFailed")
    failed_body = source[failed_at : source.index("\n        }", failed_at)]
    assert "root._pendingFederatedContent = null" in failed_body
    # 失败分支必须在联邦 Connections（不依赖 root.active）内，与成功分支同处
    failed_at = source.index("function onTextLoadFailed")
    success_at = source.index("function onTextContentLoaded")
    flag_set_at = source.index("root._pendingFederatedContent = true")
    assert failed_at > flag_set_at and success_at > flag_set_at


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
