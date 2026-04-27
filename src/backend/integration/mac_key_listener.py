"""macOS global keyboard listener based on Quartz CGEventTap."""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..ports.key_codes import KeyCodes
from ..utils.logger import log_info


class MacKeyListener(QObject):
    """Listen for macOS hardware key-down events.

    macOS requires the app or terminal to be granted Input Monitoring or
    Accessibility permission before CGEventTap can receive keyboard events.
    """

    keyPressed = Signal(int, str)

    BACKSPACE_KEYCODES = frozenset({51, 117})

    def __init__(self) -> None:
        super().__init__()
        self._quartz: Any | None = None
        self._event_tap: Any | None = None
        self._run_loop: Any | None = None
        self._thread: threading.Thread | None = None

    @staticmethod
    def is_backspace_keycode(key_code: int) -> bool:
        return key_code in MacKeyListener.BACKSPACE_KEYCODES

    @staticmethod
    def _has_shortcut_modifier(quartz: Any, event: Any) -> bool:
        flags = int(quartz.CGEventGetFlags(event))
        shortcut_masks = quartz.kCGEventFlagMaskControl | quartz.kCGEventFlagMaskCommand
        return bool(flags & shortcut_masks)

    def start(self) -> None:
        """Create the event tap and start its CFRunLoop thread."""
        if self._thread and self._thread.is_alive():
            return

        quartz = self._load_quartz()
        mask = quartz.CGEventMaskBit(quartz.kCGEventKeyDown)
        event_tap = quartz.CGEventTapCreate(
            quartz.kCGSessionEventTap,
            quartz.kCGHeadInsertEventTap,
            quartz.kCGEventTapOptionListenOnly,
            mask,
            self._handle_event,
            None,
        )
        if not event_tap:
            raise RuntimeError(
                "macOS 键盘监听不可用。请在系统设置中授予输入监控或辅助功能权限。"
            )

        self._quartz = quartz
        self._event_tap = event_tap
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="typetype-macos-key-listener",
            daemon=True,
        )
        self._thread.start()
        log_info("macOS 全局键盘监听器已启动")

    def stop(self) -> None:
        """Stop the listener run loop."""
        if self._quartz and self._event_tap:
            self._quartz.CGEventTapEnable(self._event_tap, False)
        if self._quartz and self._run_loop:
            self._quartz.CFRunLoopStop(self._run_loop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None
        self._run_loop = None
        self._event_tap = None
        log_info("macOS 全局键盘监听器已停止")

    @staticmethod
    def _load_quartz() -> Any:
        try:
            import Quartz
        except ImportError as exc:
            raise RuntimeError(
                "缺少 macOS Quartz 监听依赖，请安装 pyobjc-framework-Quartz。"
            ) from exc
        return Quartz

    def _run_event_loop(self) -> None:
        quartz = self._quartz
        event_tap = self._event_tap
        if not quartz or not event_tap:
            return

        source = quartz.CFMachPortCreateRunLoopSource(None, event_tap, 0)
        self._run_loop = quartz.CFRunLoopGetCurrent()
        quartz.CFRunLoopAddSource(
            self._run_loop,
            source,
            quartz.kCFRunLoopCommonModes,
        )
        quartz.CGEventTapEnable(event_tap, True)
        quartz.CFRunLoopRun()

    def _handle_event(
        self, proxy: Any, event_type: int, event: Any, refcon: Any
    ) -> Any:
        quartz = self._quartz
        if not quartz:
            return event

        if event_type in (
            quartz.kCGEventTapDisabledByTimeout,
            quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._event_tap:
                quartz.CGEventTapEnable(self._event_tap, True)
            return event

        key_code = int(
            quartz.CGEventGetIntegerValueField(
                event,
                quartz.kCGKeyboardEventKeycode,
            )
        )

        if event_type == quartz.kCGEventKeyDown:
            normalized_key_code = KeyCodes.macos_keycode(key_code)
            if self._has_shortcut_modifier(quartz, event) and not KeyCodes.is_backspace(
                normalized_key_code
            ):
                return event
            self.keyPressed.emit(normalized_key_code, "macOS keyboard")
        return event
