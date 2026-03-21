"""Bridge 模块测试。"""

from PySide6.QtCore import QObject, Signal

from src.backend.presentation.bridge import Bridge
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.domain.services.char_stats_service import CharStatsService
from src.backend.domain.services.typing_service import TypingService
from src.backend.domain.services.auth_service import AuthService
from src.backend.integration.noop_char_stats_repository import NoopCharStatsRepository
from src.backend.application.usecases.typing_usecase import TypingUseCase
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.application.gateways.score_gateway import ScoreGateway
from src.backend.application.gateways.text_gateway import TextGateway
from src.backend.presentation.adapters.typing_adapter import TypingAdapter
from src.backend.presentation.adapters.text_adapter import TextAdapter
from src.backend.integration.global_key_listener import GlobalKeyListener
from unittest.mock import MagicMock
from typing import cast


class DummyListener(QObject):
    keyPressed = Signal(int, str)


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
        text_gateway = MagicMock(spec=TextGateway)
        text_gateway.get_source_options.return_value = []
        text_gateway.get_default_source_key.return_value = "builtin_demo"

        # UseCases
        typing_usecase = TypingUseCase(score_gateway=score_gateway)
        load_text_usecase = LoadTextUseCase(gateway=text_gateway)

        # Adapters
        typing_adapter = TypingAdapter(
            typing_service=typing_service,
            typing_usecase=typing_usecase,
        )
        text_adapter = TextAdapter(
            text_gateway=text_gateway,
            load_text_usecase=load_text_usecase,
        )

        return typing_adapter, text_adapter, auth_service

    def test_bridge_without_listener(self):
        """未传监听器时，应为普通平台"""
        typing_adapter, text_adapter, auth_service = self._create_mock_services()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=None,
        )
        assert bridge.isSpecialPlatform is False

    def test_bridge_with_listener(self):
        """传入监听器时，应标记为特殊平台"""
        typing_adapter, text_adapter, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=cast(GlobalKeyListener, listener),
        )
        assert bridge.isSpecialPlatform is True

    def test_key_received_calls_handle_pressed_when_focused(self):
        typing_adapter, text_adapter, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_adapter.score_data.key_stroke_count == 1

    def test_key_received_ignored_when_not_focused(self):
        typing_adapter, text_adapter, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=cast(GlobalKeyListener, listener),
        )
        typing_adapter.handleStartStatus(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_adapter.score_data.key_stroke_count == 0
