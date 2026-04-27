from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_wenlai_previous_segment_shortcut_matches_typesunny_ctrl_o():
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"
    lower_pane = PROJECT_ROOT / "src/qml/typing/LowerPane.qml"

    typing_page_source = typing_page.read_text(encoding="utf-8")
    lower_pane_source = lower_pane.read_text(encoding="utf-8")

    assert "event.key === Qt.Key_O" in typing_page_source
    assert "event.key === Qt.Key_O" in lower_pane_source


def test_enter_shortcut_toggles_typing_pause():
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"
    lower_pane = PROJECT_ROOT / "src/qml/typing/LowerPane.qml"

    typing_page_source = typing_page.read_text(encoding="utf-8")
    lower_pane_source = lower_pane.read_text(encoding="utf-8")

    assert "Qt.Key_Return" in typing_page_source
    assert "Qt.Key_Enter" in typing_page_source
    assert "toggleTypingPause()" in typing_page_source
    assert "Qt.Key_Return" in lower_pane_source
    assert "Qt.Key_Enter" in lower_pane_source
    assert "toggleTypingPause()" in lower_pane_source


def test_main_window_auto_pauses_when_deactivated():
    main_qml = PROJECT_ROOT / "src/qml/Main.qml"

    source = main_qml.read_text(encoding="utf-8")

    assert "onActiveChanged" in source
    assert "pauseTypingFromWindowDeactivate()" in source


def test_settings_manual_wenlai_mode_prompt_matches_typesunny():
    settings_page = PROJECT_ROOT / "src/qml/pages/SettingsPage.qml"

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
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"

    typing_page_source = typing_page.read_text(encoding="utf-8")

    assert "Shortcut" in typing_page_source
    assert 'sequence: "Ctrl+R"' in typing_page_source
    assert 'sequence: "Meta+R"' in typing_page_source
    assert "triggerRandomWenlaiText()" in typing_page_source
    assert "appBridge.loadRandomWenlaiText()" in typing_page_source
    assert 'sequence: "Ctrl+O"' in typing_page_source
    assert 'sequence: "Ctrl+P"' in typing_page_source
    assert "triggerPrevSegment()" in typing_page_source
    assert "triggerNextSegment()" in typing_page_source


def test_wenlai_button_is_disabled_and_spinner_only_while_loading():
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"
    tool_line = PROJECT_ROOT / "src/qml/typing/ToolLine.qml"

    typing_page_source = typing_page.read_text(encoding="utf-8")
    tool_line_source = tool_line.read_text(encoding="utf-8")

    assert "wenlaiStatusText" not in typing_page_source
    assert "正在获取晴发文..." not in typing_page_source
    assert "晴发文获取成功" not in typing_page_source
    assert (
        "wenlaiLoading: appBridge ? appBridge.wenlaiLoading : false"
        in typing_page_source
    )
    assert "wenlaiLoading" in tool_line_source
    assert "enabled: !root.wenlaiLoading" in tool_line_source
    assert 'text: "晴发文[C^R]"' in tool_line_source
    assert "running: root.wenlaiLoading" in tool_line_source
    assert "visible: root.wenlaiLoading" in tool_line_source
    assert "获取中..." not in tool_line_source
    assert "wenlaiStatusText" not in tool_line_source


def test_realtime_score_area_does_not_show_wenlai_segment_or_copy_score():
    score_area = PROJECT_ROOT / "src/qml/typing/ScoreArea.qml"

    source = score_area.read_text(encoding="utf-8")

    assert "id: segmentNo" not in source
    assert "appBridge.wenlaiSegmentLabel" not in source
    assert "copyScoreMessage()" not in source


def test_history_area_shows_wenlai_segment_and_right_click_copies_record_score():
    history_area = PROJECT_ROOT / "src/qml/typing/HistoryArea.qml"

    source = history_area.read_text(encoding="utf-8")

    assert '"段号"' in source
    assert 'TableModelColumn { display: "segmentNo" }' in source
    assert 'TableModelColumn { display: "speed" }' in source
    assert source.index('display: "segmentNo"') < source.index('display: "speed"')
    assert "Qt.RightButton" in source
    assert "copyToClipboard(rowData.scoreText)" in source
    assert "copyToast.show()" in source
    assert "已复制到剪贴板" in source


def test_history_area_uses_explicit_resizable_column_widths():
    history_area = PROJECT_ROOT / "src/qml/typing/HistoryArea.qml"

    source = history_area.read_text(encoding="utf-8")

    assert "resizableColumns: true" in source
    assert "columnWidthProvider" not in source
    assert "setColumnWidth" in source
    assert "resetColumnWidths" in source


def test_titlebar_drag_area_is_enabled_with_native_mac_controls():
    title_bar = PROJECT_ROOT / "RinUI/windows/TitleBar.qml"

    source = title_bar.read_text(encoding="utf-8")

    assert "enabled: root.window !== null" in source
    assert "startSystemMove()" in source


def test_typing_end_copies_score_without_opening_end_dialog():
    typing_page = PROJECT_ROOT / "src/qml/pages/TypingPage.qml"

    source = typing_page.read_text(encoding="utf-8")

    assert "copyScoreMessage()" in source
    assert "endDialog.open()" not in source
    assert (
        "copyAggregateScore()" not in source
    )  # 聚合成绩复制在 EndDialog 中，TypingPage 不再直接调用
