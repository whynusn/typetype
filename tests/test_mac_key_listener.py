"""macOS key listener pure logic tests."""

from src.backend.integration.mac_key_listener import MacKeyListener
from src.backend.ports.key_codes import KeyCodes


class FakeEvent:
    def __init__(self, key_code: int, flags: int = 0) -> None:
        self.key_code = key_code
        self.flags = flags


class FakeQuartz:
    kCGEventKeyDown = 10
    kCGEventFlagsChanged = 12
    kCGEventTapDisabledByTimeout = -1
    kCGEventTapDisabledByUserInput = -2
    kCGKeyboardEventKeycode = 99
    kCGEventFlagMaskShift = 1 << 17
    kCGEventFlagMaskControl = 1 << 18
    kCGEventFlagMaskAlternate = 1 << 19
    kCGEventFlagMaskCommand = 1 << 20

    @staticmethod
    def CGEventGetIntegerValueField(event: FakeEvent | int, field: int) -> int:
        if isinstance(event, FakeEvent):
            return event.key_code
        return int(event)

    @staticmethod
    def CGEventGetFlags(event: FakeEvent | int) -> int:
        if isinstance(event, FakeEvent):
            return event.flags
        return 0


def test_macos_backspace_keycode_is_recognized() -> None:
    assert MacKeyListener.is_backspace_keycode(51) is True


def test_macos_forward_delete_keycode_is_recognized() -> None:
    assert MacKeyListener.is_backspace_keycode(117) is True


def test_non_delete_keycode_is_not_backspace() -> None:
    assert MacKeyListener.is_backspace_keycode(0) is False


def test_key_down_event_emits_keycode() -> None:
    listener = MacKeyListener()
    listener._quartz = FakeQuartz
    events: list[int] = []
    listener.keyPressed.connect(lambda key_code, device: events.append(key_code))

    listener._handle_event(None, FakeQuartz.kCGEventKeyDown, 0, None)

    assert events == [KeyCodes.macos_keycode(0)]


def test_modifier_flags_changed_does_not_emit_keycode() -> None:
    listener = MacKeyListener()
    listener._quartz = FakeQuartz
    events: list[int] = []
    listener.keyPressed.connect(lambda key_code, device: events.append(key_code))

    listener._handle_event(None, FakeQuartz.kCGEventFlagsChanged, 56, None)

    assert events == []


def test_command_shortcut_key_down_does_not_emit_keycode() -> None:
    listener = MacKeyListener()
    listener._quartz = FakeQuartz
    events: list[int] = []
    listener.keyPressed.connect(lambda key_code, device: events.append(key_code))

    listener._handle_event(
        None,
        FakeQuartz.kCGEventKeyDown,
        FakeEvent(8, FakeQuartz.kCGEventFlagMaskCommand),
        None,
    )

    assert events == []


def test_shift_modified_key_down_still_emits_keycode() -> None:
    listener = MacKeyListener()
    listener._quartz = FakeQuartz
    events: list[int] = []
    listener.keyPressed.connect(lambda key_code, device: events.append(key_code))

    listener._handle_event(
        None,
        FakeQuartz.kCGEventKeyDown,
        FakeEvent(0, FakeQuartz.kCGEventFlagMaskShift),
        None,
    )

    assert events == [KeyCodes.macos_keycode(0)]
