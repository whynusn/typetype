"""
SystemIdentifier 模块测试
"""

from types import SimpleNamespace

from src.backend.integration.system_identifier import SystemIdentifier


class TestSystemIdentifier:
    """测试系统信息识别逻辑"""

    def test_windows_short_circuit(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Windows"
        )
        assert SystemIdentifier().get_system_info() == ("Windows", "N/A")

    def test_macos_short_circuit(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Darwin"
        )
        assert SystemIdentifier().get_system_info() == ("macOS", "N/A")

    def test_linux_wayland_by_env(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.os.environ",
            {"WAYLAND_DISPLAY": "wayland-0"},
        )

        assert SystemIdentifier().get_system_info() == ("Linux", "Wayland")

    def test_linux_x11_by_env(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.os.environ",
            {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"},
        )

        assert SystemIdentifier().get_system_info() == ("Linux", "X11")

    def test_linux_xwayland_by_env(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.os.environ",
            {"DISPLAY": ":0", "XDG_SESSION_TYPE": "wayland"},
        )

        assert SystemIdentifier().get_system_info() == ("Linux", "Wayland (XWayland)")

    def test_linux_detect_by_loginctl_wayland(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.os.environ", {"XDG_SESSION_ID": "1"}
        )

        monkeypatch.setattr(
            "src.backend.integration.system_identifier.subprocess.run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="Type=wayland\n"
            ),
        )

        assert SystemIdentifier().get_system_info() == ("Linux", "Wayland")

    def test_linux_detect_by_loginctl_x11(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.os.environ", {"XDG_SESSION_ID": "2"}
        )

        monkeypatch.setattr(
            "src.backend.integration.system_identifier.subprocess.run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Type=x11\n"),
        )

        assert SystemIdentifier().get_system_info() == ("Linux", "X11")

    def test_linux_loginctl_exception_fallback_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.system_identifier.platform.system", lambda: "Linux"
        )
        monkeypatch.setattr("src.backend.integration.system_identifier.os.environ", {})

        def raise_error(*args, **kwargs):
            raise RuntimeError("loginctl unavailable")

        monkeypatch.setattr("src.backend.integration.system_identifier.subprocess.run", raise_error)

        assert SystemIdentifier().get_system_info() == ("Linux", "Unknown")
