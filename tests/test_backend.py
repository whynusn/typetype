"""
Bridge 模块测试（包含原 Backend 功能）
"""

from PySide6.QtCore import QObject, Signal

from src.backend.text_properties import Bridge
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.domain.typing_service import TypingService
from src.backend.domain.text_load_service import TextLoadService
from src.backend.domain.auth_service import AuthService
from src.backend.application.usecases.score_usecase import ScoreUseCase
from src.backend.application.usecases.text_usecase import TextUseCase
from unittest.mock import MagicMock


class DummyListener(QObject):
    """用于模拟全局键盘监听器"""

    keyPressed = Signal(int, str)


class TestBridgeSpecialPlatform:
    """测试 Bridge 平台特殊性处理（原 Backend 职责）"""

    def _create_mock_services(self):
        score_usecase = MagicMock(spec=ScoreUseCase)
        typing_service = TypingService(score_usecase=score_usecase)
        text_usecase = MagicMock(spec=TextUseCase)
        text_load_service = TextLoadService(
            text_usecase=text_usecase, runtime_config=RuntimeConfig()
        )
        auth_service = MagicMock(spec=AuthService)
        auth_service.initialize.return_value = None
        auth_service.is_logged_in = False
        return typing_service, text_load_service, auth_service

    def test_bridge_without_listener(self):
        """未传监听器时，应为普通平台"""
        typing_service, text_load_service, auth_service = self._create_mock_services()
        bridge = Bridge(
            typing_service=typing_service,
            text_load_service=text_load_service,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=None,
        )
        assert bridge.isSpecialPlatform is False

    def test_bridge_with_listener(self):
        """传入监听器时，应标记为特殊平台"""
        typing_service, text_load_service, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_service=typing_service,
            text_load_service=text_load_service,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=listener,
        )
        assert bridge.isSpecialPlatform is True

    def test_key_received_calls_handle_pressed_when_focused(self):
        typing_service, text_load_service, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_service=typing_service,
            text_load_service=text_load_service,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=listener,
        )
        typing_service.handleStartStatus(True)
        bridge.setLowerPaneFocused(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_service._score_data.key_stroke_count == 1

    def test_key_received_ignored_when_not_focused(self):
        typing_service, text_load_service, auth_service = self._create_mock_services()
        listener = DummyListener()
        bridge = Bridge(
            typing_service=typing_service,
            text_load_service=text_load_service,
            auth_service=auth_service,
            runtime_config=RuntimeConfig(),
            key_listener=listener,
        )
        typing_service.handleStartStatus(True)
        bridge.on_key_received(65, "kbd0")
        assert typing_service._score_data.key_stroke_count == 0
