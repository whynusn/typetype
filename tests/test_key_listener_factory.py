"""Key listener factory selection tests."""

from src.backend.integration.key_listener_factory import create_key_listener


class DummyListener:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_linux_wayland_uses_linux_listener() -> None:
    listener = DummyListener()

    result = create_key_listener(
        os_type="Linux",
        display_server="Wayland",
        linux_listener_factory=lambda: listener,
        macos_listener_factory=lambda: None,
    )

    assert result is listener


def test_linux_x11_does_not_use_global_listener() -> None:
    result = create_key_listener(
        os_type="Linux",
        display_server="X11",
        linux_listener_factory=DummyListener,
        macos_listener_factory=DummyListener,
    )

    assert result is None


def test_macos_uses_macos_listener() -> None:
    listener = DummyListener()

    result = create_key_listener(
        os_type="macOS",
        display_server="N/A",
        linux_listener_factory=lambda: None,
        macos_listener_factory=lambda: listener,
    )

    assert result is listener


def test_listener_factory_failure_falls_back_to_none() -> None:
    def fail() -> DummyListener:
        raise RuntimeError("missing permission")

    result = create_key_listener(
        os_type="macOS",
        display_server="N/A",
        linux_listener_factory=DummyListener,
        macos_listener_factory=fail,
    )

    assert result is None
