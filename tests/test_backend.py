"""Bridge 模块测试。"""

from PySide6.QtCore import QObject, Signal
from dataclasses import dataclass

from src.backend.presentation.bridge import Bridge
from src.backend.domain.services.char_stats_service import CharStatsService
from src.backend.domain.services.typing_service import TypingService
from src.backend.domain.services.auth_service import AuthService
from src.backend.integration.noop_char_stats_repository import NoopCharStatsRepository
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.application.gateways.score_gateway import ScoreGateway
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.models.dto.fetched_text import FetchedText
from src.backend.presentation.adapters.typing_adapter import TypingAdapter
from src.backend.presentation.adapters.text_adapter import TextAdapter
from src.backend.presentation.adapters.auth_adapter import AuthAdapter
from src.backend.presentation.adapters.char_stats_adapter import CharStatsAdapter
from src.backend.integration.global_key_listener import GlobalKeyListener
from unittest.mock import MagicMock
from typing import cast


class DummyListener(QObject):
    keyPressed = Signal(int, str)


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

    def test_backspace_key_accumulates_backspace_and_key_stroke(self):
        """退格键（keyCode=14）应同时累积退格次数和击键数"""
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
        bridge.on_key_received(14, "kbd0")
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
