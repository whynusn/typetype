import time
from unittest.mock import MagicMock, patch

from src.backend.domain.services.auth_service import AuthService
from src.backend.models.dto.auth_dto import AuthResult


# Patch SecureStorage globally for all tests (no keyring backend in sandbox)
_secure_storage_patcher = patch.multiple(
    "src.backend.security.secure_storage.SecureStorage",
    save_jwt=MagicMock(),
    get_jwt=MagicMock(return_value=None),
)
_secure_storage_patcher.start()


def _make_provider(
    login_result: AuthResult | None = None,
    refresh_result: AuthResult | None = None,
    validate_result: AuthResult | None = None,
) -> MagicMock:
    provider = MagicMock()
    provider.login.return_value = login_result or AuthResult(success=False)
    provider.refresh_token.return_value = refresh_result or AuthResult(success=False)
    provider.validate_token.return_value = validate_result or AuthResult(success=False)
    return provider


class TestAuthServiceRefreshInterval:
    def test_refresh_interval_zero_when_no_expires_in(self):
        provider = _make_provider()
        svc = AuthService(auth_provider=provider)
        assert svc.refresh_interval_seconds == 0

    def test_refresh_interval_normal(self):
        provider = _make_provider(
            login_result=AuthResult(
                success=True,
                access_token="a",
                refresh_token="r",
                expires_in=900,
                user_info={"id": "1", "nickname": "test"},
            )
        )
        svc = AuthService(auth_provider=provider)
        with patch.object(svc, "_auth_provider", provider):
            svc.login("u", "p")
        # 900 - 120 = 780
        assert svc.refresh_interval_seconds == 780

    def test_refresh_interval_minimum_60(self):
        provider = _make_provider(
            login_result=AuthResult(
                success=True,
                access_token="a",
                refresh_token="r",
                expires_in=100,
                user_info={"id": "1", "nickname": "test"},
            )
        )
        svc = AuthService(auth_provider=provider)
        with patch.object(svc, "_auth_provider", provider):
            svc.login("u", "p")
        # 100 - 120 = -20 -> max(-20, 60) = 60
        assert svc.refresh_interval_seconds == 60


class TestAuthTokenRemaining:
    def test_remaining_zero_when_not_logged_in(self):
        provider = _make_provider()
        svc = AuthService(auth_provider=provider)
        assert svc.token_remaining_seconds == 0

    def test_remaining_decreases_over_time(self):
        provider = _make_provider(
            login_result=AuthResult(
                success=True,
                access_token="a",
                refresh_token="r",
                expires_in=900,
                user_info={"id": "1", "nickname": "test"},
            )
        )
        svc = AuthService(auth_provider=provider)
        with patch.object(svc, "_auth_provider", provider):
            svc.login("u", "p")
        # Immediately after login, remaining should be close to 900
        remaining = svc.token_remaining_seconds
        assert 899 <= remaining <= 900

    def test_remaining_updates_on_refresh(self):
        provider = _make_provider(
            login_result=AuthResult(
                success=True,
                access_token="a",
                refresh_token="r",
                expires_in=900,
                user_info={"id": "1", "nickname": "test"},
            ),
            refresh_result=AuthResult(
                success=True,
                access_token="a2",
                refresh_token="r2",
                expires_in=900,
                user_info={"id": "1", "username": "test", "nickname": "test"},
            ),
        )
        svc = AuthService(auth_provider=provider)
        with patch.object(svc, "_auth_provider", provider):
            svc.login("u", "p")
            # Manually set issued_at to simulate time passing
            svc._token_issued_at = time.monotonic() - 400
            before = svc.token_remaining_seconds
            assert before < 900
            svc.refresh_token()
            after = svc.token_remaining_seconds
            # After refresh, remaining should be reset (close to 900)
            assert after >= before


class TestAuthLogoutReset:
    def test_logout_resets_expires_state(self):
        provider = _make_provider(
            login_result=AuthResult(
                success=True,
                access_token="a",
                refresh_token="r",
                expires_in=900,
                user_info={"id": "1", "nickname": "test"},
            )
        )
        svc = AuthService(auth_provider=provider)
        with patch.object(svc, "_auth_provider", provider):
            svc.login("u", "p")
        assert svc.refresh_interval_seconds == 780
        with patch("src.backend.domain.services.auth_service.keyring.delete_password"):
            svc.logout()
        assert svc.refresh_interval_seconds == 0
        assert svc.token_remaining_seconds == 0
