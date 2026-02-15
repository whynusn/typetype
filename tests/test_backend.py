"""
Backend 模块测试
"""

from PySide6.QtCore import QObject, Signal

from src.backend.backend import Backend


class DummyListener(QObject):
    """用于模拟全局键盘监听器"""

    keyPressed = Signal(int, str)


class TestBackend:
    """测试 Backend 行为"""

    def test_backend_without_listener(self):
        """未传监听器时，应为普通平台"""
        backend = Backend()
        assert backend.isSpecialPlatform is False

    def test_backend_with_listener(self):
        """传入监听器时，应标记为特殊平台"""
        listener = DummyListener()
        backend = Backend(listener)
        assert backend.isSpecialPlatform is True

    def test_forward_key_signal_from_listener(self):
        """监听器按键信号应转发到 Backend.keyPressed"""
        listener = DummyListener()
        backend = Backend(listener)

        received = []
        backend.keyPressed.connect(lambda code, name: received.append((code, name)))

        listener.keyPressed.emit(65, "kbd0")

        assert received == [(65, "kbd0")]

    def test_on_key_received_emit(self):
        """直接调用 on_key_received 应触发 keyPressed"""
        backend = Backend()

        received = []
        backend.keyPressed.connect(lambda code, name: received.append((code, name)))

        backend.on_key_received(66, "kbd1")

        assert received == [(66, "kbd1")]
