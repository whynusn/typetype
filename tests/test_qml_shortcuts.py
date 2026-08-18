"""QML shortcut Bridge API introspection tests."""

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = PROJECT_ROOT / "src/backend/presentation/bridge.py"
QML_DIR = PROJECT_ROOT / "src/qml"
RINUI_DIR = PROJECT_ROOT / "RinUI"


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


def test_wenlai_previous_segment_shortcut_matches_typesunny_ctrl_o():
    typing_page = QML_DIR / "pages/TypingPage.qml"
    lower_pane = QML_DIR / "typing/LowerPane.qml"
    tp_source = typing_page.read_text(encoding="utf-8")
    lp_source = lower_pane.read_text(encoding="utf-8")
    assert "event.key === Qt.Key_O" in tp_source
    assert "event.key === Qt.Key_O" in lp_source


def test_enter_shortcut_toggles_typing_pause():
    typing_page = QML_DIR / "pages/TypingPage.qml"
    lower_pane = QML_DIR / "typing/LowerPane.qml"
    tp_source = typing_page.read_text(encoding="utf-8")
    lp_source = lower_pane.read_text(encoding="utf-8")
    assert "Qt.Key_Return" in tp_source
    assert "Qt.Key_Enter" in tp_source
    assert "Qt.Key_Return" in lp_source
    assert "Qt.Key_Enter" in lp_source
    assert "toggleTypingPause" in BRIDGE_SLOTS


def test_lower_pane_rejects_middle_cursor_edits():
    source = (QML_DIR / "typing/LowerPane.qml").read_text(encoding="utf-8")
    assert "textArea.cursorPosition < currentText.length" in source
    assert "textArea.text = root.lastText" in source


def test_main_window_auto_pauses_when_deactivated():
    main_qml = QML_DIR / "Main.qml"
    source = main_qml.read_text(encoding="utf-8")
    assert "onActiveChanged" in source
    assert "pauseTypingFromWindowDeactivate" in BRIDGE_SLOTS


def test_settings_manual_wenlai_mode_prompt_matches_typesunny():
    settings_page = QML_DIR / "pages/SettingsPage.qml"
    source = settings_page.read_text(encoding="utf-8")
    assert 'title: qsTr("晴发文换段模式")' in source
    assert "手动换段模式：" in source
    assert "打完后不会自动发下一段" in source
    assert "Ctrl+P" in source
    assert "Ctrl+O" in source
    assert "Ctrl+R" in source
    assert "继续随机一段" in source
    assert "wenlaiManualModeDialog.open()" in source


def test_window_level_shortcuts_drive_wenlai_actions_without_text_focus():
    typing_page = QML_DIR / "pages/TypingPage.qml"
    source = typing_page.read_text(encoding="utf-8")
    refs = _get_qml_refs(source)
    assert "Shortcut" in source
    assert 'sequence: "Ctrl+R"' in source
    assert 'sequence: "Meta+R"' in source
    assert "triggerRandomWenlaiText()" in source
    assert "loadRandomWenlaiText" in refs and "loadRandomWenlaiText" in BRIDGE_SLOTS
    assert 'sequence: "Ctrl+O"' in source
    assert 'sequence: "Ctrl+P"' in source
    assert "triggerPrevSegment()" in source
    assert "triggerNextSegment()" in source


def test_wenlai_button_is_disabled_and_spinner_only_while_loading():
    typing_page = QML_DIR / "pages/TypingPage.qml"
    tool_line = QML_DIR / "typing/ToolLine.qml"
    tp_refs = _get_qml_refs(typing_page.read_text(encoding="utf-8"))
    tl_source = tool_line.read_text(encoding="utf-8")
    assert "wenlaiLoading" in tp_refs and "wenlaiLoading" in BRIDGE_PROPERTIES
    assert "wenlaiLoading" in tl_source
    assert "enabled: !root.wenlaiLoading" in tl_source
    assert 'text: "晴发文[C^R]"' in tl_source
    assert "running: root.wenlaiLoading" in tl_source
    assert "visible: root.wenlaiLoading" in tl_source


def test_realtime_score_area_does_not_show_wenlai_segment_or_copy_score():
    score_area = QML_DIR / "typing/ScoreArea.qml"
    source = score_area.read_text(encoding="utf-8")
    assert "id: segmentNo" not in source
    assert (
        "wenlaiSegmentLabel" not in BRIDGE_PROPERTIES
        or "wenlaiSegmentLabel" not in source
    )
    assert "copyScoreMessage()" not in source


def test_history_area_shows_wenlai_segment_and_right_click_copies_record_score():
    history_area = QML_DIR / "typing/HistoryArea.qml"
    source = history_area.read_text(encoding="utf-8")
    assert '"段号"' in source
    assert 'TableModelColumn { display: "segmentNo" }' in source
    assert 'TableModelColumn { display: "speed" }' in source
    assert source.index('display: "segmentNo"') < source.index('display: "speed"')
    assert "Qt.RightButton" in source
    assert "copyToClipboard(rowData.scoreText)" in source
    assert "appNotificationManager.show" in source
    assert "已复制到剪贴板" in source


def test_history_area_uses_explicit_resizable_column_widths():
    history_area = QML_DIR / "typing/HistoryArea.qml"
    source = history_area.read_text(encoding="utf-8")
    assert "resizableColumns: true" in source
    assert "columnWidthProvider" not in source
    assert "setColumnWidth" in source
    assert "resetColumnWidths" in source


def test_titlebar_drag_area_is_enabled_with_native_mac_controls():
    title_bar = RINUI_DIR / "windows/TitleBar.qml"
    source = title_bar.read_text(encoding="utf-8")
    assert "enabled: root.window !== null" in source
    assert "startSystemMove()" in source


def test_ai_recommend_button_shows_ctrl_e_shortcut():
    tool_line = PROJECT_ROOT / "src/qml/typing/ToolLine.qml"
    tl = tool_line.read_text(encoding="utf-8")
    assert 'text: "AI 推荐[^E]"' in tl
    assert "enabled: !root.aiTextLoading" in tl
    assert "requestAiText()" in tl


def test_ctrl_e_shortcut_triggers_ai_text():
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"
    tp = typing_page.read_text(encoding="utf-8")
    assert "event.key === Qt.Key_E" in tp
    assert "appBridge.requestAiText()" in tp
    assert 'sequence: "Ctrl+E"' in tp
    assert 'sequence: "Meta+E"' in tp


def test_tool_line_has_no_load_text_button():
    tool_line = PROJECT_ROOT / "src/qml/typing/ToolLine.qml"
    tl = tool_line.read_text(encoding="utf-8")
    assert "载文[F2]" not in tl
    assert "requestOpenSliceConfig" in tl  # signal still kept


def test_typing_end_copies_score_without_opening_end_dialog():
    typing_page = QML_DIR / "pages/TypingPage.qml"
    source = typing_page.read_text(encoding="utf-8")
    assert "copyScoreMessage" in BRIDGE_SLOTS
    assert "endDialog.open()" not in source
    assert "copyAggregateScore" in BRIDGE_SLOTS
    assert "copyAggregateScore()" not in source
