"""Normalized keycode constants for platform key listeners."""

from __future__ import annotations


class KeyCodes:
    """Platform keycode constants used by global key listeners."""

    MACOS_KEY_OFFSET = 10_000

    # Linux input event codes.
    EVDEV_BACKSPACE = 14
    EVDEV_LEFT_CTRL = 29
    EVDEV_LEFT_SHIFT = 42
    EVDEV_RIGHT_SHIFT = 54
    EVDEV_LEFT_ALT = 56
    EVDEV_CAPS_LOCK = 58
    EVDEV_RIGHT_CTRL = 97
    EVDEV_RIGHT_ALT = 100
    EVDEV_LEFT_META = 125
    EVDEV_RIGHT_META = 126
    EVDEV_COMPOSE = 127

    # Navigation keys (evdev key codes)
    EVDEV_HOME = 102
    EVDEV_UP = 103
    EVDEV_PAGEUP = 104
    EVDEV_LEFT = 105
    EVDEV_RIGHT = 106
    EVDEV_END = 107
    EVDEV_DOWN = 108
    EVDEV_PAGEDOWN = 109
    EVDEV_INSERT = 110
    EVDEV_DELETE = 111

    # macOS navigation keycodes
    MACOS_HOME = MACOS_KEY_OFFSET + 115
    MACOS_PAGEUP = MACOS_KEY_OFFSET + 116
    MACOS_END = MACOS_KEY_OFFSET + 119
    MACOS_PAGEDOWN = MACOS_KEY_OFFSET + 121
    MACOS_LEFT_ARROW = MACOS_KEY_OFFSET + 123
    MACOS_RIGHT_ARROW = MACOS_KEY_OFFSET + 124
    MACOS_DOWN_ARROW = MACOS_KEY_OFFSET + 125
    MACOS_UP_ARROW = MACOS_KEY_OFFSET + 126

    # macOS hardware keycodes namespaced to avoid collisions with evdev codes.
    MACOS_BACKSPACE = MACOS_KEY_OFFSET + 51
    MACOS_FORWARD_DELETE = MACOS_KEY_OFFSET + 117
    MACOS_RIGHT_COMMAND = MACOS_KEY_OFFSET + 54
    MACOS_LEFT_COMMAND = MACOS_KEY_OFFSET + 55
    MACOS_LEFT_SHIFT = MACOS_KEY_OFFSET + 56
    MACOS_CAPS_LOCK = MACOS_KEY_OFFSET + 57
    MACOS_LEFT_OPTION = MACOS_KEY_OFFSET + 58
    MACOS_LEFT_CONTROL = MACOS_KEY_OFFSET + 59
    MACOS_RIGHT_SHIFT = MACOS_KEY_OFFSET + 60
    MACOS_RIGHT_OPTION = MACOS_KEY_OFFSET + 61
    MACOS_RIGHT_CONTROL = MACOS_KEY_OFFSET + 62
    MACOS_FUNCTION = MACOS_KEY_OFFSET + 63

    BACKSPACE_KEYS = frozenset({EVDEV_BACKSPACE, MACOS_BACKSPACE, MACOS_FORWARD_DELETE})
    MODIFIER_KEYS = frozenset(
        {
            EVDEV_LEFT_CTRL,
            EVDEV_LEFT_SHIFT,
            EVDEV_RIGHT_SHIFT,
            EVDEV_LEFT_ALT,
            EVDEV_CAPS_LOCK,
            EVDEV_RIGHT_CTRL,
            EVDEV_RIGHT_ALT,
            EVDEV_LEFT_META,
            EVDEV_RIGHT_META,
            EVDEV_COMPOSE,
            MACOS_RIGHT_COMMAND,
            MACOS_LEFT_COMMAND,
            MACOS_LEFT_SHIFT,
            MACOS_CAPS_LOCK,
            MACOS_LEFT_OPTION,
            MACOS_LEFT_CONTROL,
            MACOS_RIGHT_SHIFT,
            MACOS_RIGHT_OPTION,
            MACOS_RIGHT_CONTROL,
            MACOS_FUNCTION,
        }
    )
    SHORTCUT_MODIFIER_KEYS = frozenset(
        {
            EVDEV_LEFT_CTRL,
            EVDEV_RIGHT_CTRL,
            EVDEV_LEFT_META,
            EVDEV_RIGHT_META,
            MACOS_RIGHT_COMMAND,
            MACOS_LEFT_COMMAND,
            MACOS_LEFT_CONTROL,
            MACOS_RIGHT_CONTROL,
        }
    )

    @classmethod
    def macos_keycode(cls, key_code: int) -> int:
        return cls.MACOS_KEY_OFFSET + key_code

    NAVIGATION_KEYS = frozenset(
        {
            EVDEV_HOME,
            EVDEV_UP,
            EVDEV_PAGEUP,
            EVDEV_LEFT,
            EVDEV_RIGHT,
            EVDEV_END,
            EVDEV_DOWN,
            EVDEV_PAGEDOWN,
            EVDEV_INSERT,
            EVDEV_DELETE,
            MACOS_HOME,
            MACOS_PAGEUP,
            MACOS_END,
            MACOS_PAGEDOWN,
            MACOS_LEFT_ARROW,
            MACOS_RIGHT_ARROW,
            MACOS_DOWN_ARROW,
            MACOS_UP_ARROW,
        }
    )

    @classmethod
    def is_backspace(cls, key_code: int) -> bool:
        return key_code in cls.BACKSPACE_KEYS

    @classmethod
    def is_modifier(cls, key_code: int) -> bool:
        return key_code in cls.MODIFIER_KEYS

    @classmethod
    def is_navigation(cls, key_code: int) -> bool:
        """返回 True 如果按键是导航键（不产生文本的键）。"""
        return key_code in cls.NAVIGATION_KEYS

    @classmethod
    def is_shortcut_modifier(cls, key_code: int) -> bool:
        return key_code in cls.SHORTCUT_MODIFIER_KEYS
