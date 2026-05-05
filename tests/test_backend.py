"""Bridge 模块测试。"""

from PySide6.QtCore import QObject, Signal
from dataclasses import dataclass

from src.backend.ports.key_codes import KeyCodes
from src.backend.presentation.bridge import Bridge
from src.backend.domain.services.char_stats_service import CharStatsService
from src.backend.domain.services.typing_service import TypingService
from src.backend.domain.services.auth_service import AuthService
from src.backend.integration.noop_char_stats_repository import NoopCharStatsRepository
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.application.gateways.score_gateway import ScoreGateway
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.models.dto.fetched_text import FetchedText
from src.backend.models.dto.wenlai_dto import WenlaiText
from src.backend.presentation.adapters.typing_adapter import TypingAdapter
from src.backend.presentation.adapters.text_adapter import TextAdapter
from src.backend.presentation.adapters.auth_adapter import AuthAdapter
from src.backend.presentation.adapters.char_stats_adapter import CharStatsAdapter
from src.backend.integration.global_key_listener import GlobalKeyListener
from src.backend.application.session_context import TypingSessionContext
from unittest.mock import MagicMock
from typing import cast


class DummyListener(QObject):
    keyPressed = Signal(int, str)


class DummyWenlaiAdapter(QObject):
    textLoaded = Signal(str, str)
    loadFailed = Signal(str)
    loadingChanged = Signal()
    loginResult = Signal(bool, str)
    loginStateChanged = Signal()
    configChanged = Signal()
    difficultiesLoaded = Signal(list)
    categoriesLoaded = Signal(list)

    def __init__(self):
        super().__init__()
        self._current_text: WenlaiText | None = None
        self._is_active = False
        self.clear_count = 0
        self.load_random_count = 0
        self.load_next_count = 0
        self._text_loading = False

    @property
    def loading(self) -> bool:
        return False

    @property
    def text_loading(self) -> bool:
        return self._text_loading

    @property
    def logged_in(self) -> bool:
        return True

    @property
    def current_user(self) -> str:
        return "alice"

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def current_text(self):
        return self._current_text

    @property
    def segment_mode(self) -> str:
        return "manual"

    @property
    def base_url(self) -> str:
        return "https://wenlai.example"

    @property
    def length(self) -> int:
        return 0

    @property
    def difficulty_level(self) -> int:
        return 0

    @property
    def category(self) -> str:
        return ""

    @property
    def strict_length(self) -> bool:
        return False

    def clear_active(self) -> None:
        self.clear_count += 1
        self._current_text = None
        self._is_active = False

    def loadRandomText(self) -> None:
        self.load_random_count += 1

    def emit_loaded_text(
        self,
        text: str = "晴发文正文",
        title: str = "晴发文标题",
        mark: str = "1-2",
        sort_num: int = 1,
    ) -> None:
        self._current_text = WenlaiText(
            title=title,
            content=text,
            mark=mark,
            sort_num=sort_num,
            difficulty_label="普",
            difficulty_score=2.3,
        )
        self._is_active = True
        self.textLoaded.emit(text, title)

    def loadNextSegment(self) -> None:
        self.load_next_count += 1


class DummyLocalArticleAdapter(QObject):
    localArticlesLoaded = Signal(list)
    localArticlesLoadFailed = Signal(str)
    localArticleSegmentLoaded = Signal(dict)
    localArticleSegmentLoadFailed = Signal(str)
    localArticleLoadingChanged = Signal()

    def __init__(self):
        super().__init__()
        self.load_articles_count = 0
        self.segment_requests: list[tuple[str, int, int]] = []
        self.clear_count = 0
        self._loading = False

    @property
    def local_article_loading(self) -> bool:
        return self._loading

    def loadLocalArticles(self) -> None:
        self.load_articles_count += 1

    def loadLocalArticleSegment(
        self,
        article_id: str,
        segment_index: int,
        segment_size: int,
    ) -> None:
        self.segment_requests.append((article_id, segment_index, segment_size))

    def clear_active(self) -> None:
        self.clear_count += 1


class DummyZitiAdapter(QObject):
    schemesLoaded = Signal(list)
    schemesLoadFailed = Signal(str)
    schemeLoaded = Signal(str, int)
    schemeLoadFailed = Signal(str)
    zitiStateChanged = Signal()

    def __init__(self):
        super().__init__()
        self.load_schemes_count = 0
        self.loaded_scheme_names: list[str] = []
        self.enabled_values: list[bool] = []
        self._enabled = False
        self._current_scheme = ""
        self._loaded_count = 0
        self.hints = {"一": "yi"}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def current_scheme(self) -> str:
        return self._current_scheme

    @property
    def loaded_count(self) -> int:
        return self._loaded_count

    def loadSchemes(self) -> None:
        self.load_schemes_count += 1

    def loadScheme(self, name: str) -> None:
        self.loaded_scheme_names.append(name)
        self._current_scheme = name

    def setEnabled(self, enabled: bool) -> None:
        self.enabled_values.append(enabled)
        self._enabled = enabled
        self.zitiStateChanged.emit()

    def get_hint(self, char: str) -> str:
        return self.hints.get(char, "")


class DummyTrainerAdapter(QObject):
    trainersLoaded = Signal(list)
    trainersLoadFailed = Signal(str)
    trainerSegmentLoaded = Signal(dict)
    trainerSegmentLoadFailed = Signal(str)
    trainerLoadingChanged = Signal()

    def __init__(self):
        super().__init__()
        self.load_trainers_count = 0
        self.segment_requests: list[tuple[str, int, int]] = []
        self.current_count = 0
        self.next_count = 0
        self.previous_count = 0
        self.shuffle_count = 0
        self.clear_count = 0
        self._trainer_loading = False

    @property
    def trainer_loading(self) -> bool:
        return self._trainer_loading

    def loadTrainers(self) -> None:
        self.load_trainers_count += 1

    def loadTrainerSegment(
        self,
        trainer_id: str,
        segment_index: int,
        group_size: int,
        full_shuffle: bool = False,
    ) -> None:
        self.segment_requests.append((trainer_id, segment_index, group_size))

    def loadCurrentTrainerSegment(self) -> None:
        self.current_count += 1

    def loadNextTrainerSegment(self) -> None:
        self.next_count += 1

    def loadPreviousTrainerSegment(self) -> None:
        self.previous_count += 1

    def shuffleCurrentTrainerGroup(self) -> None:
        self.shuffle_count += 1

    def clear_active(self) -> None:
        self.clear_count += 1


class DummyTypingTotalsGateway:
    def __init__(self):
        self.today_chars = 0
        self.total_chars = 0

    def record_session(self, char_count: int) -> None:
        self.today_chars += char_count
        self.total_chars += char_count


@dataclass
class DummySource:
    key: str
    label: str = "测试来源"
    local_path: str | None = None


class TestBridgeSpecialPlatform:
    """测试 Bridge 平台特殊性处理。"""

    def _create_mock_services(self):
        # Domain Services
        char_stats_service = CharStatsService(repository=NoopCharStatsRepository())
        typing_service = TypingService(char_stats_service=char_stats_service)
        auth_service = MagicMock(spec=AuthService)
        auth_service.initialize.return_value = None
        auth_service.is_logged_in = False

        # Gateways
        score_gateway = MagicMock(spec=ScoreGateway)
        runtime_config = MagicMock(spec=RuntimeConfig)
        runtime_config.get_text_source_options.return_value = []
        runtime_config.default_text_source_key = "builtin_demo"

        text_gateway = MagicMock()
        text_gateway.plan_load.return_value = DummySource(
            key="test",
            local_path="test.txt",
        )
        text_gateway.load_from_plan.return_value = (
            True,
            FetchedText(content="test text", text_id=123, title="测试标题"),
            "",
        )

        load_text_usecase = LoadTextUseCase(
            text_gateway=text_gateway,
            clipboard_reader=MagicMock(),
        )

        typing_adapter = TypingAdapter(
            typing_service=typing_service,
            score_gateway=score_gateway,
        )
        local_text_loader = MagicMock()
        text_adapter = TextAdapter(
            runtime_config=runtime_config,
            load_text_usecase=load_text_usecase,
            local_text_loader=local_text_loader,
        )

        auth_adapter = AuthAdapter(auth_service=auth_service)
        char_stats_adapter = CharStatsAdapter(char_stats_service=char_stats_service)

        return typing_adapter, text_adapter, auth_adapter, char_stats_adapter

    def test_bridge_without_listener(self):
        """未传监听器时，应为普通平台"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        assert bridge.isSpecialPlatform is False

    def test_bridge_with_listener(self):
        """传入监听器时，应标记为特殊平台"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        assert bridge.isSpecialPlatform is True

    def test_key_received_calls_handle_pressed_when_focused(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_first_global_key_starts_session_and_counts_key(self):
        """特殊平台应从第一个物理输入键启动会话，避免漏算首个拼音键。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        bridge.setLowerPaneFocused(True)

        bridge.on_key_received(65, "kbd0")

        assert typing_adapter.is_started is True
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_global_modifier_key_is_ignored(self):
        """Shift/Ctrl/Command 等修饰键不计入打字成绩。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        bridge.setLowerPaneFocused(True)

        bridge.on_key_received(KeyCodes.EVDEV_LEFT_SHIFT, "kbd0")

        assert typing_adapter.is_started is False
        assert typing_adapter.score_data.key_stroke_count == 0

    def test_key_received_ignored_when_not_focused(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_adapter.score_data.key_stroke_count == 0

    def test_evdev_backspace_key_accumulates_backspace_and_key_stroke(self):
        """Linux evdev 退格键应同时累积退格次数和击键数。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)
        bridge.on_key_received(KeyCodes.EVDEV_BACKSPACE, "kbd0")
        assert typing_adapter.score_data.backspace_count == 1
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_evdev_comma_key_is_not_treated_as_macos_backspace(self):
        """Linux evdev 普通键码 51 不能被误判为 macOS Backspace。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)

        bridge.on_key_received(51, "linux-kbd")

        assert typing_adapter.score_data.backspace_count == 0
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_macos_backspace_key_accumulates_backspace_and_key_stroke(self):
        """macOS delete/backspace 键应同时累积退格次数和击键数。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)
        bridge.on_key_received(KeyCodes.MACOS_BACKSPACE, "mac-kbd")
        assert typing_adapter.score_data.backspace_count == 1
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_request_load_text_locks_typing_until_text_ready(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )

        typing_adapter.handleStartStatus(True)
        assert typing_adapter.text_read_only is False

        bridge.requestLoadText("test")

        assert typing_adapter.text_read_only is True

    def test_load_text_from_clipboard_locks_typing_until_text_ready(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )

        typing_adapter.handleStartStatus(True)
        assert typing_adapter.text_read_only is False

        bridge.loadTextFromClipboard()

        assert typing_adapter.text_read_only is True

    def test_pause_typing_preserves_score_and_locks_input(self):
        typing_adapter, _, _, _ = self._create_mock_services()
        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)
        typing_adapter._typing_service.score_data.char_count = 2
        typing_adapter._typing_service.score_data.key_stroke_count = 8
        events: list[bool] = []
        typing_adapter.pauseChanged.connect(
            lambda: events.append(typing_adapter.is_paused)
        )

        changed = typing_adapter.pauseTyping()

        assert changed is True
        assert typing_adapter.is_paused is True
        assert typing_adapter.is_started is False
        assert typing_adapter.text_read_only is True
        assert typing_adapter.score_data.char_count == 2
        assert typing_adapter.score_data.key_stroke_count == 8
        assert events == [True]

    def test_resume_typing_continues_paused_score(self):
        typing_adapter, _, _, _ = self._create_mock_services()
        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)
        typing_adapter._typing_service.score_data.char_count = 2
        typing_adapter._typing_service.score_data.key_stroke_count = 8
        typing_adapter.pauseTyping()
        events: list[bool] = []
        typing_adapter.pauseChanged.connect(
            lambda: events.append(typing_adapter.is_paused)
        )

        changed = typing_adapter.resumeTyping()

        assert changed is True
        assert typing_adapter.is_paused is False
        assert typing_adapter.is_started is True
        assert typing_adapter.text_read_only is False
        assert typing_adapter.score_data.char_count == 2
        assert typing_adapter.score_data.key_stroke_count == 8
        assert events == [False]

    def test_window_deactivate_pause_only_affects_running_session(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )

        assert bridge.pauseTypingFromWindowDeactivate() is False

        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)

        assert bridge.pauseTypingFromWindowDeactivate() is True
        assert bridge.typingPaused is True

    def test_setup_slice_mode_emits_slice_mode_changed(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        typing_adapter._session_context = TypingSessionContext()
        events: list[bool] = []

        bridge.sliceModeChanged.connect(lambda: events.append(bridge.sliceMode))

        bridge.setupSliceMode("天地玄黄宇宙洪荒", 4, 1, 0, 0, 0, 1, "retype")

        assert events == [True]
        assert bridge.sliceMode is True

    def test_request_shuffle_in_slice_mode_preserves_slice_state(self):
        """分片模式下点击乱序按钮应保持分片状态，不覆盖 source_mode。"""
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session

        bridge.setupSliceMode("天地玄黄宇宙洪荒", 4, 1, 0, 0, 0, 1, "retype")
        assert bridge.sliceMode is True
        assert session.source_mode.name == "SLICE"

        # 模拟分片模式下点击乱序按钮
        bridge.requestShuffle()

        # 关键断言：source_mode 应保持为 SLICE，而不是被覆盖为 SHUFFLE
        assert session.source_mode.name == "SLICE"
        assert bridge.sliceMode is True

    def test_load_next_slice_advances_by_one_slice(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        typing_adapter._session_context = TypingSessionContext()
        labels: list[str] = []

        bridge.textLoaded.connect(
            lambda text, text_id, source_label: labels.append(source_label)
        )

        bridge.setupSliceMode("一二三四五六七八九十", 2, 1, 0, 0, 0, 1, "retype")
        bridge.loadNextSlice()
        bridge.loadNextSlice()

        assert labels == ["载文 1/5", "载文 2/5", "载文 3/5"]
        assert bridge._typing_adapter._session_context.slice_index == 3

    def test_wenlai_load_preserves_active_state_for_adjacent_segments(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        loaded: list[tuple[str, int, str]] = []
        bridge.textLoaded.connect(
            lambda text, text_id, source_label: loaded.append(
                (text, text_id, source_label)
            )
        )

        wenlai_adapter.emit_loaded_text()

        assert bridge.isWenlaiActive is True
        assert wenlai_adapter.clear_count == 0
        assert loaded == [("晴发文正文", -1, "晴发文标题")]

    def test_wenlai_load_copies_sender_content(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        copied: list[str] = []
        bridge._copy_text_to_clipboard = copied.append

        wenlai_adapter.emit_loaded_text()

        assert copied == [
            "[普(2.30)]晴发文标题 [字数5]\n晴发文正文\n-----第1-2段-晴发文"
        ]

    def test_wenlai_auto_next_copies_score_and_next_sender_content(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        typing_adapter._score_gateway.build_score_plain_text.return_value = "成绩文本"
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        copied: list[str] = []
        bridge._copy_text_to_clipboard = copied.append
        wenlai_adapter.emit_loaded_text("当前段正文", "当前段标题", mark="1-2")
        copied.clear()

        bridge.loadNextWenlaiSegmentWithScore()
        wenlai_adapter.emit_loaded_text("下一段正文", "下一段标题")

        assert wenlai_adapter.load_next_count == 1
        assert copied == [
            "段1-2 成绩文本",
            "段1-2 成绩文本\n[普(2.30)]下一段标题 [字数5]\n下一段正文\n-----第1-2段-晴发文",
        ]

    def test_wenlai_copy_score_message_includes_real_segment_mark(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        typing_adapter._score_gateway.build_score_plain_text.return_value = "成绩文本"
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        copied: list[str] = []
        bridge._copy_text_to_clipboard = copied.append
        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题", mark="1-2")
        copied.clear()

        bridge.copyScoreMessage()

        assert copied == ["段1-2 成绩文本"]

    def test_wenlai_window_title_includes_difficulty_and_title_without_segment(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )

        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题")
        typing_adapter._typing_service.set_total_chars(5)

        assert bridge.windowTitle == "TypeType 普(2.30) 0/5 晴发文标题"

    def test_wenlai_segment_label_exposes_current_text_progress(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )

        assert bridge.wenlaiSegmentLabel == ""

        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题")

        assert bridge.wenlaiSegmentLabel == "1/2"

    def test_wenlai_segment_label_falls_back_to_sort_num_without_mark(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )

        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题", mark="", sort_num=8)

        assert bridge.wenlaiSegmentLabel == "8"

    def test_wenlai_segment_label_change_signal_emits_when_text_loads(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        labels: list[str] = []
        bridge.wenlaiSegmentLabelChanged.connect(
            lambda: labels.append(bridge.wenlaiSegmentLabel)
        )

        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题")

        assert labels[-1] == "1/2"

    def test_history_record_includes_wenlai_segment_and_copyable_score_text(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        typing_adapter._score_gateway.build_score_plain_text.return_value = "成绩文本"
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        records: list[dict] = []
        bridge.historyRecordUpdated.connect(records.append)
        wenlai_adapter.emit_loaded_text("晴发文正文", "晴发文标题")

        typing_adapter.typingEnded.emit()
        typing_adapter.historyRecordUpdated.emit({"speed": 1.23})

        assert records == [
            {"speed": 1.23, "segmentNo": "1/2", "scoreText": "段1-2 成绩文本"}
        ]

    def test_history_record_updates_persistent_typing_totals(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        totals_gateway = DummyTypingTotalsGateway()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            typing_totals_gateway=totals_gateway,
            key_listener=None,
        )
        records: list[dict] = []
        totals_events: list[tuple[int, int]] = []
        bridge.historyRecordUpdated.connect(records.append)
        bridge.typingTotalsChanged.connect(
            lambda: totals_events.append(
                (bridge.todayTypedChars, bridge.totalTypedChars)
            )
        )

        typing_adapter.historyRecordUpdated.emit({"charNum": 42})

        assert records == [{"charNum": 42}]
        assert bridge.todayTypedChars == 42
        assert bridge.totalTypedChars == 42
        assert totals_events == [(42, 42)]

    def test_collect_slice_result_populates_session_context(self):
        """collectSliceResult 必须将 _last_slice_stats 快照存入 session_context。

        回归测试：防止 get_last_slice_stats 被错误代理到 session_context 导致
        在 collect_slice_result 调用前返回空字典，从而使惩罚条件永远失效。
        """
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session

        # 模拟打完一片后的状态：_last_slice_stats 已被 _check_typing_complete 捕获
        fake_stats = {"speed": 100.0, "keyAccuracy": 95.0, "wrong_char_count": 0}
        typing_adapter._last_slice_stats = fake_stats

        # 设置分片模式（否则 collect_slice_result 中的 session_context 检查不通过）
        session.setup_slice_mode("天地玄黄", 4, 1, 0, 0, 98, 1, "retype")

        # 关键断言：get_last_slice_stats 必须在 collect_slice_result 之前
        # 返回 _last_slice_stats（快照），而不是 session_context 中空的 _slice_stats
        assert typing_adapter.get_last_slice_stats() == fake_stats

        bridge.collectSliceResult()

        # 验证数据已正确存入 session_context
        assert len(session._slice_stats) == 1
        assert session._slice_stats[0]["speed"] == 100.0
        assert session.should_retype() is True  # keyAccuracy 95 < 98，应触发重打

    def test_local_article_segment_prepares_local_non_ranking_typing_session(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        local_article_adapter = DummyLocalArticleAdapter()
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )
        loaded_segments: list[dict] = []
        loaded_texts: list[tuple[str, int, str]] = []
        bridge.localArticleSegmentLoaded.connect(loaded_segments.append)
        bridge.textLoaded.connect(
            lambda content, text_id, label: loaded_texts.append(
                (content, text_id, label)
            )
        )
        bridge.setupSliceMode("天地玄黄宇宙洪荒", 4, 1, 0, 0, 0, 1, "retype")
        wenlai_adapter.emit_loaded_text()
        bridge.setTextId(88)
        clear_count_before_segment = wenlai_adapter.clear_count

        payload = {
            "articleId": "a1",
            "title": "长文",
            "content": "片段内容",
            "index": 2,
            "total": 5,
        }
        local_article_adapter.localArticleSegmentLoaded.emit(payload)

        assert bridge.sliceMode is True
        assert wenlai_adapter.clear_count == clear_count_before_segment
        assert bridge.textId == 0
        assert session.source_mode.name == "SLICE"
        assert session.upload_status.name == "NA"
        assert session.can_submit_score() is False
        assert loaded_segments == [payload]
        assert loaded_texts[-1] == ("片段内容", -1, "长文 2/5")
        assert typing_adapter.text_title == "长文 2/5"

    def test_stale_local_text_id_resolution_is_ignored_for_local_article_session(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )
        local_article_adapter.localArticleSegmentLoaded.emit(
            {
                "articleId": "a1",
                "title": "长文",
                "content": "片段内容",
                "index": 1,
                "total": 2,
            }
        )

        text_adapter.localTextIdResolved.emit(
            999, text_adapter.current_lookup_generation
        )

        assert bridge.textId == 0
        assert session.upload_status.name == "NA"
        assert session.can_submit_score() is False

    def test_queued_stale_local_text_id_resolution_is_ignored_after_new_local_load(
        self,
    ):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )
        text_adapter.invalidate_pending_text_id_lookup()
        stale_generation = text_adapter.current_lookup_generation

        bridge.requestLoadText("test")
        text_adapter.textLoaded.emit("新本地文本", -1, "新本地")
        text_adapter.localTextIdResolved.emit(111, stale_generation)

        assert bridge.textId == 0
        assert session.source_mode.name == "LOCAL"
        assert session.upload_status.name == "PENDING"

    def test_current_local_text_id_resolution_confirms_standard_local_session(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            key_listener=None,
        )

        bridge.requestLoadText("test")
        text_adapter.textLoaded.emit("新本地文本", -1, "新本地")
        text_adapter.invalidate_pending_text_id_lookup()
        current_generation = text_adapter.current_lookup_generation
        text_adapter.localTextIdResolved.emit(222, current_generation)

        assert bridge.textId == 222
        assert session.upload_status.name == "CONFIRMED"

    def test_request_load_text_invalidates_pending_local_article_results(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )

        bridge.requestLoadText("test")

        assert local_article_adapter.clear_count >= 1

    def test_load_local_article_segment_locks_input_before_worker_finishes(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )
        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)
        assert typing_adapter.text_read_only is False

        bridge.loadLocalArticleSegment("a1", 1, 500)

        assert local_article_adapter.segment_requests == [("a1", 1, 500)]
        assert typing_adapter.text_read_only is True
        assert bridge.textId == 0
        assert session.source_mode.name == "LOCAL_ARTICLE"

    def test_wenlai_load_request_locks_input_before_worker_finishes(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)
        assert typing_adapter.text_read_only is False

        bridge.loadRandomWenlaiText()

        assert wenlai_adapter.load_random_count == 1
        assert typing_adapter.text_read_only is True

    def test_wenlai_duplicate_load_request_is_ignored_at_bridge_boundary(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        wenlai_adapter = DummyWenlaiAdapter()
        wenlai_adapter._text_loading = True
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            key_listener=None,
        )
        typing_adapter._typing_service.set_total_chars(4)
        typing_adapter.handleStartStatus(True)
        assert typing_adapter.text_read_only is False

        bridge.loadRandomWenlaiText()
        bridge.loadNextWenlaiSegmentWithScore()

        assert wenlai_adapter.load_random_count == 0
        assert wenlai_adapter.load_next_count == 0
        assert typing_adapter.text_read_only is False

    def test_bridge_forwards_local_article_catalog_slots_and_signals(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )
        catalogs: list[list] = []
        failures: list[str] = []
        bridge.localArticlesLoaded.connect(catalogs.append)
        bridge.localArticlesLoadFailed.connect(failures.append)

        bridge.loadLocalArticles()
        bridge.loadLocalArticleSegment("a1", 3, 500)
        local_article_adapter.localArticlesLoaded.emit([{"articleId": "a1"}])
        local_article_adapter.localArticlesLoadFailed.emit("失败")

        assert local_article_adapter.load_articles_count == 1
        assert local_article_adapter.segment_requests == [("a1", 3, 500)]
        assert catalogs == [[{"articleId": "a1"}]]
        assert failures == ["失败"]

    def test_bridge_forwards_ziti_slots_signals_and_properties(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        ziti_adapter = DummyZitiAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            ziti_adapter=ziti_adapter,
            key_listener=None,
        )
        schemes: list[list] = []
        scheme_failures: list[str] = []
        loaded: list[tuple[str, int]] = []
        bridge.zitiSchemesLoaded.connect(schemes.append)
        bridge.zitiSchemeLoadFailed.connect(scheme_failures.append)
        bridge.zitiSchemeLoaded.connect(
            lambda name, count: loaded.append((name, count))
        )

        bridge.loadZitiSchemes()
        bridge.loadZitiScheme("小鹤")
        bridge.setZitiEnabled(True)
        ziti_adapter.schemesLoaded.emit([{"name": "小鹤", "entryCount": 1}])
        ziti_adapter.schemeLoadFailed.emit("失败")
        ziti_adapter.schemeLoaded.emit("小鹤", 1)

        assert ziti_adapter.load_schemes_count == 1
        assert ziti_adapter.loaded_scheme_names == ["小鹤"]
        assert ziti_adapter.enabled_values == [True]
        assert bridge.zitiEnabled is True
        assert bridge.zitiCurrentScheme == "小鹤"
        assert bridge.getZitiHint("一") == "yi"
        assert schemes == [[{"name": "小鹤", "entryCount": 1}]]
        assert scheme_failures == ["失败"]
        assert loaded == [("小鹤", 1)]

    def test_bridge_forwards_trainer_catalog_slots_signals_and_properties(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        trainer_adapter = DummyTrainerAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            trainer_adapter=trainer_adapter,
            key_listener=None,
        )
        catalogs: list[list] = []
        failures: list[str] = []
        bridge.trainersLoaded.connect(catalogs.append)
        bridge.trainersLoadFailed.connect(failures.append)

        bridge.loadTrainers()
        trainer_adapter.trainersLoaded.emit([{"trainerId": "t1"}])
        trainer_adapter.trainersLoadFailed.emit("失败")

        assert trainer_adapter.load_trainers_count == 1
        assert bridge.trainerLoading is False
        assert catalogs == [[{"trainerId": "t1"}]]
        assert failures == ["失败"]

    def test_trainer_segment_prepares_non_ranking_typing_session(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        trainer_adapter = DummyTrainerAdapter()
        wenlai_adapter = DummyWenlaiAdapter()
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            wenlai_adapter=wenlai_adapter,
            local_article_adapter=local_article_adapter,
            trainer_adapter=trainer_adapter,
            key_listener=None,
        )
        loaded_segments: list[dict] = []
        loaded_texts: list[tuple[str, int, str]] = []
        bridge.trainerSegmentLoaded.connect(loaded_segments.append)
        bridge.textLoaded.connect(
            lambda content, text_id, label: loaded_texts.append(
                (content, text_id, label)
            )
        )
        bridge.setupSliceMode("天地玄黄宇宙洪荒", 4, 1, 0, 0, 0, 1, "retype")
        wenlai_adapter.emit_loaded_text()
        bridge.setTextId(88)

        bridge.loadTrainerSegment("t1", 2, 20)
        payload = {
            "trainerId": "t1",
            "title": "前500",
            "content": "天地玄黄",
            "index": 2,
            "total": 25,
            "groupSize": 20,
        }
        trainer_adapter.trainerSegmentLoaded.emit(payload)

        assert bridge.sliceMode is True
        assert trainer_adapter.segment_requests == [("t1", 2, 20)]
        assert local_article_adapter.clear_count == 1
        assert bridge.textId == 0
        assert session.source_mode.name == "SLICE"
        assert session.upload_status.name == "NA"
        assert session.can_submit_score() is False
        assert session.on_fail_action == "retype"
        assert loaded_segments == [payload]
        assert loaded_texts[-1] == ("天地玄黄", -1, "前500 2/25")
        assert typing_adapter.text_title == "前500 2/25"

    def test_setup_slice_mode_clears_sourced_backend_flags(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        trainer_adapter = DummyTrainerAdapter()
        local_article_adapter = DummyLocalArticleAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            trainer_adapter=trainer_adapter,
            local_article_adapter=local_article_adapter,
            key_listener=None,
        )

        # 模拟之前处于 trainer sourced 分片上下文
        bridge._coordinator.source_slice_backend = "trainer"
        bridge._coordinator.source_slice_trainer_id = "t1"
        bridge._coordinator.source_slice_group_size = 20

        # 切到 TypingPage 文本型分片
        bridge.setupSliceMode("天地玄黄宇宙洪荒", 4, 1, 0, 0, 0, 1, "retype")

        # 失败重打应走文本型 reload，不应回调 trainer adapter
        bridge.handleSliceRetype()

        assert bridge._coordinator.source_slice_backend is None
        assert bridge._coordinator.source_slice_trainer_id == ""
        assert trainer_adapter.segment_requests == []

    def test_typing_completed_clears_cursor_before_typing_ended(self):
        typing_adapter, _, _, _ = self._create_mock_services()
        session = TypingSessionContext()
        typing_adapter._session_context = session

        typing_adapter._typing_service.set_total_chars(1)
        typing_adapter._typing_service.set_plain_doc("中")
        typing_adapter._typing_service.state.is_started = True

        # 模拟已存在 cursor 但本次输入不触发着色路径（避免依赖 QTextCursor）
        typing_adapter._cursor = object()

        cursor_is_none_during_emit: list[bool] = []

        def _on_typing_ended() -> None:
            cursor_is_none_during_emit.append(typing_adapter._cursor is None)

        typing_adapter.typingEnded.connect(_on_typing_ended)

        original_handle = typing_adapter._typing_service.handle_committed_text

        def _complete_without_updates(
            s: str, grow_length: int
        ) -> tuple[list[tuple[int, str, bool]], bool]:
            updates, _ = original_handle(s, grow_length)
            return [], True

        typing_adapter._typing_service.handle_committed_text = _complete_without_updates
        try:
            typing_adapter.handleCommittedText("中", 1)
        finally:
            typing_adapter._typing_service.handle_committed_text = original_handle

        assert cursor_is_none_during_emit == [True]

    def test_bridge_forwards_trainer_navigation_slots(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        trainer_adapter = DummyTrainerAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            trainer_adapter=trainer_adapter,
            key_listener=None,
        )

        bridge.loadCurrentTrainerSegment()
        bridge.loadNextTrainerSegment()
        bridge.loadPreviousTrainerSegment()
        bridge.shuffleCurrentTrainerGroup()

        assert trainer_adapter.current_count == 1
        assert trainer_adapter.next_count == 1
        assert trainer_adapter.previous_count == 1
        assert trainer_adapter.shuffle_count == 1

    def test_trainer_retype_uses_current_segment_not_reload(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        trainer_adapter = DummyTrainerAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            trainer_adapter=trainer_adapter,
            key_listener=None,
        )

        bridge._coordinator.source_slice_backend = "trainer"
        bridge._coordinator.source_slice_trainer_id = "t1"
        bridge._coordinator.source_slice_group_size = 20
        typing_adapter.setup_sourced_slice_mode(
            slice_index=2,
            slice_total=10,
            on_fail_action="retype",
            key_stroke_min=0,
            speed_min=0,
            accuracy_min=0,
            pass_count_min=1,
        )

        bridge.handleSliceRetype()

        assert trainer_adapter.current_count == 1
        assert trainer_adapter.segment_requests == []

    def test_trainer_shuffle_retype_uses_shuffle_current_group(self):
        typing_adapter, text_adapter, auth_adapter, char_stats_adapter = (
            self._create_mock_services()
        )
        session = TypingSessionContext()
        typing_adapter._session_context = session
        trainer_adapter = DummyTrainerAdapter()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_adapter=auth_adapter,
            char_stats_adapter=char_stats_adapter,
            trainer_adapter=trainer_adapter,
            key_listener=None,
        )

        bridge._coordinator.source_slice_backend = "trainer"
        bridge._coordinator.source_slice_trainer_id = "t1"
        bridge._coordinator.source_slice_group_size = 20
        typing_adapter.setup_sourced_slice_mode(
            slice_index=2,
            slice_total=10,
            on_fail_action="shuffle",
            key_stroke_min=0,
            speed_min=0,
            accuracy_min=0,
            pass_count_min=1,
        )

        bridge.handleSliceRetype()

        assert trainer_adapter.shuffle_count == 1
        assert trainer_adapter.segment_requests == []
