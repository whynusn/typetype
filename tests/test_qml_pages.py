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
    # textListLoading/loadTextList/loadCatalog 已随 typetype-server 耦合移除
    # （ADR-013）；目录功能由联邦 loadFederatedEntries 承担
    assert "localArticleLoading" in refs and "localArticleLoading" in BRIDGE_PROPERTIES
    assert "trainerLoading" in refs and "trainerLoading" in BRIDGE_PROPERTIES
    assert "loadLocalArticles" in refs and "loadLocalArticles" in BRIDGE_SLOTS
    assert "loadTrainers" in refs and "loadTrainers" in BRIDGE_SLOTS
    assert (
        "loadLocalArticleSegment" in refs and "loadLocalArticleSegment" in BRIDGE_SLOTS
    )
    assert "loadTrainerSegment" in refs and "loadTrainerSegment" in BRIDGE_SLOTS
    # OTT 源仓库联邦聚合 Slot（hub 直接浏览/载入联邦条目）
    assert "loadFederatedEntries" in refs and "loadFederatedEntries" in BRIDGE_SLOTS
    assert (
        "loadFederatedEntrySegment" in refs
        and "loadFederatedEntrySegment" in BRIDGE_SLOTS
    )
    assert (
        "loadFederatedInlineEntry" in refs
        and "loadFederatedInlineEntry" in BRIDGE_SLOTS
    )
    # 总刷新（全部源强制换新）与订阅源级刷新（该 repo 全部源换新）都接在 hub
    assert "refreshFederatedAll" in refs and "refreshFederatedAll" in BRIDGE_SLOTS
    assert "refreshFederatedRepo" in refs and "refreshFederatedRepo" in BRIDGE_SLOTS
    # 晴发文 / AI 即时拉取入口纳入载文中心
    assert "loadRandomWenlaiText" in refs and "loadRandomWenlaiText" in BRIDGE_SLOTS
    assert "requestAiText" in refs and "requestAiText" in BRIDGE_SLOTS
    # 订阅管理收敛到源组头弹窗（RepoConfigDialog，独立管理页已取消）：
    # 添加订阅入口在 hub，启用/信任/删除在弹窗
    assert "addRepo" in refs and "addRepo" in BRIDGE_SLOTS
    config_qml = QML_DIR / "components/RepoConfigDialog.qml"
    config_refs = _get_qml_refs(config_qml.read_text(encoding="utf-8"))
    assert "removeRepo" in config_refs and "removeRepo" in BRIDGE_SLOTS
    assert "setRepoEnabled" in config_refs and "setRepoEnabled" in BRIDGE_SLOTS
    assert "confirmRepoTrust" in config_refs and "confirmRepoTrust" in BRIDGE_SLOTS
    assert "rejectRepoTrust" in config_refs and "rejectRepoTrust" in BRIDGE_SLOTS
    assert "getRepos" in config_refs and "getRepos" in BRIDGE_SLOTS
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


def test_text_load_hub_clears_federated_busy_on_load_failure():
    """联邦载文失败时 federatedContentLoading（载入跟打 Busy）必须清零。

    2026-08-14 链路改造：联邦条目载文改为后端同步直发 textLoaded
    （镜像本地文库链路），不再经 textContentLoaded/_pendingFederatedContent
    间接回传；失败/成功统一在常驻联邦 Connections 里清 busy，避免
    规则源「一直显示加载动画」。
    """
    page_qml = QML_DIR / "pages/TextLoadHubPage.qml"
    source = page_qml.read_text(encoding="utf-8")
    assert "textLoadFailed" in BRIDGE_SIGNALS
    assert "function onTextLoadFailed" in source
    assert "textLoaded" in BRIDGE_SIGNALS
    assert "function onTextLoaded" in source
    # 失败 handler 清除 busy（组件外需 root. 前缀）
    failed_at = source.index("function onTextLoadFailed")
    failed_body = source[failed_at : source.index("\n        }", failed_at)]
    assert "root.federatedContentLoading = false" in failed_body
    # 成功 handler（textLoaded 落地）同样清除 busy
    loaded_at = source.index("function onTextLoaded")
    loaded_body = source[loaded_at : source.index("\n        }", loaded_at)]
    assert "root.federatedContentLoading = false" in loaded_body
    # 常驻联邦 Connections 不依赖 root.active（页面已被 push 到 TypingPage）
    assert "// ---- 联邦跨页面信号（不依赖 root.active）----" in source


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
