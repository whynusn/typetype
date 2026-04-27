"""
GlobalKeyListener 纯逻辑测试（不依赖真实设备）
"""

from types import SimpleNamespace

from PySide6.QtCore import QObject

from src.backend.integration.global_key_listener import GlobalKeyListener
from src.backend.ports.key_codes import KeyCodes


class FakeDevice:
    """模拟输入设备"""

    def __init__(self, caps, events=None):
        self._caps = caps
        self._events = events or []
        self.fd = 1
        self.name = "fake-keyboard"

    def capabilities(self):
        return self._caps

    def read(self):
        return self._events


class FakeEvent:
    def __init__(self, event_type, code, value):
        self.type = event_type
        self.code = code
        self.value = value


class TestGlobalKeyListenerLogic:
    """测试键盘识别逻辑"""

    def _listener_with_ecodes(self):
        listener = GlobalKeyListener.__new__(GlobalKeyListener)
        listener.ecodes = SimpleNamespace(EV_KEY=1, EV_REL=2, EV_ABS=3)
        return listener

    def _listener_with_signal(self):
        listener = self._listener_with_ecodes()
        QObject.__init__(listener)
        listener._pressed_shortcut_modifiers = {}
        return listener

    def test_is_keyboard_strict_true(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30, 48]})
        assert listener._is_keyboard_strict(dev) is True
        assert listener._is_keyboard_permissive(dev) is True

    def test_is_keyboard_missing_ev_key(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({2: [0, 1]})
        assert listener._is_keyboard_strict(dev) is False
        assert listener._is_keyboard_permissive(dev) is False

    def test_is_keyboard_false_when_has_ev_rel(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30], 2: [0, 1]})
        assert listener._is_keyboard_strict(dev) is False
        assert listener._is_keyboard_permissive(dev) is False

    def test_is_keyboard_strict_excludes_ev_abs(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30], 3: [0, 1]})
        assert listener._is_keyboard_strict(dev) is False
        assert listener._is_keyboard_permissive(dev) is True

    def test_is_keyboard_false_when_only_high_keycodes(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [300, 400]})
        assert listener._is_keyboard_strict(dev) is False
        assert listener._is_keyboard_permissive(dev) is False

    def test_classify_device_keyboard(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [1, 30, 48]})
        assert listener._classify_device(dev) == "keyboard"

    def test_classify_device_mouse(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({1: [272], 2: [0, 1]})
        assert listener._classify_device(dev) == "mouse"

    def test_classify_device_touchpad(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({3: [0, 1]})
        assert listener._classify_device(dev) == "non-keyboard"

    def test_classify_device_non_keyboard(self):
        listener = self._listener_with_ecodes()
        dev = FakeDevice({2: [0, 1]})
        assert listener._classify_device(dev) == "non-keyboard"

    def test_control_shortcut_letter_is_not_emitted(self):
        listener = self._listener_with_signal()
        events = [
            FakeEvent(1, KeyCodes.EVDEV_LEFT_CTRL, 1),
            FakeEvent(1, 46, 1),
        ]
        dev = FakeDevice({1: [KeyCodes.EVDEV_LEFT_CTRL, 46]}, events)
        emitted: list[int] = []
        listener.keyPressed.connect(lambda key_code, device: emitted.append(key_code))

        listener._handle_events(dev)

        assert emitted == [KeyCodes.EVDEV_LEFT_CTRL]

    def test_shift_modified_letter_is_emitted(self):
        listener = self._listener_with_signal()
        events = [
            FakeEvent(1, KeyCodes.EVDEV_LEFT_SHIFT, 1),
            FakeEvent(1, 30, 1),
        ]
        dev = FakeDevice({1: [KeyCodes.EVDEV_LEFT_SHIFT, 30]}, events)
        emitted: list[int] = []
        listener.keyPressed.connect(lambda key_code, device: emitted.append(key_code))

        listener._handle_events(dev)

        assert emitted == [KeyCodes.EVDEV_LEFT_SHIFT, 30]
