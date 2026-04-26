"""Factory for platform-specific global keyboard listeners."""

from __future__ import annotations

from collections.abc import Callable

from ..ports.key_listener import KeyListener
from ..utils.logger import log_info


def create_key_listener(
    os_type: str,
    display_server: str,
    linux_listener_factory: Callable[[], KeyListener],
    macos_listener_factory: Callable[[], KeyListener],
) -> KeyListener | None:
    """Create and start the global key listener for platforms that need it."""
    factory: Callable[[], KeyListener] | None = None

    if os_type == "Linux" and display_server.startswith("Wayland"):
        factory = linux_listener_factory
    elif os_type == "macOS":
        factory = macos_listener_factory

    if factory is None:
        return None

    try:
        listener = factory()
        listener.start()
        return listener
    except Exception as exc:
        log_info(f"全局监听器启动失败，将使用 QML 按键回退: {exc}")
        return None
