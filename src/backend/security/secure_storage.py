import json
import logging
from pathlib import Path

import keyring
import keyring.backends.fail
import keyring.errors
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class SecureStorage:
    SERVICE_NAME = "TypeType"

    # 密钥环不可用的原因（探测一次即缓存，避免每次调用都打日志）
    _unavailable_reason: str | None = None
    _probed: bool = False

    @staticmethod
    def is_available() -> bool:
        """密钥环后端是否可用。

        无头 Linux / 未装 gnome-keyring/kwallet / dbus 缺失等环境下
        keyring 无可用后端，读写都会抛异常——凭据存储是**可选**能力，
        不可用时应降级而非让应用起不来。

        探测要点：无后端时 ``get_keyring()`` **不抛异常**，返回的是
        ``keyring.backends.fail.Keyring``（其读写一律抛 NoKeyringError）；
        不能用真实读写去探测——macOS 上会触发钥匙串解锁弹窗。
        """
        if SecureStorage._unavailable_reason is not None:
            return False
        if not SecureStorage._probed:
            SecureStorage._probed = True
            try:
                backend = keyring.get_keyring()
            except Exception as exc:
                SecureStorage._unavailable_reason = f"{type(exc).__name__}: {exc}"
            else:
                if isinstance(backend, keyring.backends.fail.Keyring):
                    SecureStorage._unavailable_reason = (
                        "无可用密钥环后端（keyring.backends.fail）"
                    )
        return SecureStorage._unavailable_reason is None

    @staticmethod
    def unavailable_reason() -> str | None:
        """密钥环不可用的原因（可用时返回 None），供诊断/日志使用。"""
        SecureStorage.is_available()
        return SecureStorage._unavailable_reason

    @staticmethod
    def _warn_unavailable(exc: BaseException) -> None:
        if SecureStorage._unavailable_reason is None:
            # 实测到不可用：记录下来，此后 is_available() 直接返回 False
            SecureStorage._unavailable_reason = f"{type(exc).__name__}: {exc}"
        reason = SecureStorage._unavailable_reason
        logger.warning(
            "系统密钥环不可用（%s）：凭据无法持久化/读取，"
            "已降级为「未存储」——登录态在本次会话内仍有效，重启后需重新登录",
            reason,
        )

    @staticmethod
    def save_jwt(user_id: str, jwt_token: str) -> bool:
        """存储到系统密钥环（macOS Keychain/Windows Credential/Linux SecretService）。

        返回是否写入成功：密钥环不可用时返回 False 并告警，不抛出——
        登录流程不该被"没有密钥环后端"打断。
        """
        try:
            keyring.set_password(
                SecureStorage.SERVICE_NAME, f"jwt_{user_id}", jwt_token
            )
        except Exception as exc:
            SecureStorage._warn_unavailable(exc)
            return False
        return True

    @staticmethod
    def get_jwt(user_id: str) -> str | None:
        """读取 token；密钥环不可用或不存在时返回 None（不抛出）。"""
        try:
            return keyring.get_password(SecureStorage.SERVICE_NAME, f"jwt_{user_id}")
        except Exception as exc:
            SecureStorage._warn_unavailable(exc)
            return None

    @staticmethod
    def delete_jwt(user_id: str) -> bool:
        """删除 token；条目本就不存在视为成功（幂等），密钥环不可用返回 False。"""
        try:
            keyring.delete_password(SecureStorage.SERVICE_NAME, f"jwt_{user_id}")
        except keyring.errors.PasswordDeleteError:
            # 条目不存在：删除语义已满足，不算失败
            return True
        except Exception as exc:
            SecureStorage._warn_unavailable(exc)
            return False
        return True

    @staticmethod
    def save_encrypted_data(data: dict, file_path: Path, password: str):
        """加密存储业务敏感数据"""
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        # 从密码派生密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"fixed_salt_should_be_random",  # 生产环境用随机盐
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

        # 加密
        f = Fernet(key)
        encrypted = f.encrypt(json.dumps(data).encode())

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(encrypted)

    @staticmethod
    def load_encrypted_data(file_path: Path, password: str) -> dict:
        """解密读取"""
        # ... 逆向过程
        pass
