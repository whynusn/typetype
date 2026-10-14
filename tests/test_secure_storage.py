import keyring.errors

from src.backend.security.secure_storage import SecureStorage
from src.backend.integration.secure_token_store import SecureTokenStore


def _reset_keyring_probe():
    """重置可用性探测缓存（每个用例前都应是干净状态）。"""
    SecureStorage._probed = False
    SecureStorage._unavailable_reason = None


def test_keyring_unavailable_degrades_instead_of_crashing(monkeypatch):
    """无密钥环后端（无头 Linux / 未装 keyring 后端）时不得抛异常。

    实测：这类机器上 keyring.get_password 抛 NoKeyringError，曾经让
    typetype 在 create_infra 阶段直接崩掉、完全起不来。凭据是可选能力，
    读不到就当"未存储"。
    """

    def boom(*_args, **_kwargs):
        raise keyring.errors.NoKeyringError("No recommended backend was available.")

    monkeypatch.setattr(
        "src.backend.security.secure_storage.keyring.get_password", boom
    )
    monkeypatch.setattr(
        "src.backend.security.secure_storage.keyring.set_password", boom
    )
    _reset_keyring_probe()

    assert SecureStorage.get_jwt("current_user") is None
    assert SecureStorage.save_jwt("current_user", "jwt-token") is False
    assert SecureStorage.unavailable_reason()


def test_secure_token_store_survives_keyring_failure(monkeypatch):
    """启动路径必读 token——密钥环不可用时应拿到 None 并缓存，不炸。"""

    def boom(*_args, **_kwargs):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr(
        "src.backend.security.secure_storage.keyring.get_password", boom
    )
    _reset_keyring_probe()
    store = SecureTokenStore()

    assert store.get_token("current_user") is None
    assert store.get_token("current_user") is None


def test_delete_jwt_treats_missing_entry_as_success(monkeypatch):
    """删除不存在的条目（PasswordDeleteError）应视为幂等成功。

    后端对"条目不存在"抛异常，登出路径曾因此崩溃。
    """

    def boom(*_args, **_kwargs):
        raise keyring.errors.PasswordDeleteError("password not found")

    monkeypatch.setattr(
        "src.backend.security.secure_storage.keyring.delete_password", boom
    )
    _reset_keyring_probe()

    assert SecureStorage.delete_jwt("wenlai_user") is True


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
