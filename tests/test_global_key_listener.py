"""
GlobalKeyListener 纯逻辑测试（不依赖真实设备）
"""

from types import SimpleNamespace

from src.backend.global_key_listener import GlobalKeyListener


class FakeDevice:
    """模拟输入设备"""

    def __init__(self, caps):
        self._caps = caps

    def capabilities(self):
        return self._caps


class TestGlobalKeyListenerLogic:
    """测试键盘识别逻辑"""

    def _listener_with_ecodes(self):
        listener = GlobalKeyListener.__new__(GlobalKeyListener)
        listener.ecodes = SimpleNamespace(EV_KEY=1, EV_REL=2, EV_ABS=3)
        return listener

    def test_is_keyboard_true(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30, 48]})
        assert listener._is_keyboard(dev) is True

    def test_is_keyboard_missing_ev_key(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({2: [0, 1]})
        assert listener._is_keyboard(dev) is False

    def test_is_keyboard_false_when_has_ev_rel(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30], 2: [0, 1]})
        assert listener._is_keyboard(dev) is False

    def test_is_keyboard_false_when_has_ev_abs(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30], 3: [0, 1]})
        assert listener._is_keyboard(dev) is False

    def test_is_keyboard_false_when_only_high_keycodes(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [300, 400]})
        assert listener._is_keyboard(dev) is False
