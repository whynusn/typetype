from src.backend.security.secure_storage import SecureStorage
from src.backend.integration.secure_token_store import SecureTokenStore


def test_delete_jwt_uses_secure_storage_key(monkeypatch):
    deleted: list[tuple[str, str]] = []

    def fake_delete_password(service_name: str, key: str) -> None:
        deleted.append((service_name, key))

    monkeypatch.setattr(
        "src.backend.security.secure_storage.keyring.delete_password",
        fake_delete_password,
    )

    SecureStorage.delete_jwt("wenlai_user")

    assert deleted == [(SecureStorage.SERVICE_NAME, "jwt_wenlai_user")]


def test_secure_token_store_caches_loaded_tokens(monkeypatch):
    loaded_keys: list[str] = []

    def fake_get_jwt(key: str) -> str:
        loaded_keys.append(key)
        return f"token-{key}"

    monkeypatch.setattr(
        "src.backend.integration.secure_token_store.SecureStorage.get_jwt",
        fake_get_jwt,
    )
    store = SecureTokenStore()

    assert store.get_token("wenlai_user") == "token-wenlai_user"
    assert store.get_token("wenlai_user") == "token-wenlai_user"
    assert loaded_keys == ["wenlai_user"]


def test_secure_token_store_updates_cache_on_save_and_delete(monkeypatch):
    saved: list[tuple[str, str]] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        "src.backend.integration.secure_token_store.SecureStorage.save_jwt",
        lambda key, token: saved.append((key, token)),
    )
    monkeypatch.setattr(
        "src.backend.integration.secure_token_store.SecureStorage.delete_jwt",
        lambda key: deleted.append(key),
    )
    store = SecureTokenStore()

    store.save_token("wenlai_user", "new-token")
    assert store.get_token("wenlai_user") == "new-token"

    store.delete_token("wenlai_user")

    assert store.get_token("wenlai_user") is None
    assert saved == [("wenlai_user", "new-token")]
    assert deleted == ["wenlai_user"]
