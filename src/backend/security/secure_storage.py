import json
from pathlib import Path

import keyring
from cryptography.fernet import Fernet


class SecureStorage:
    SERVICE_NAME = "TypeType"

    @staticmethod
    def save_jwt(user_id: str, jwt_token: str):
        """存储到系统密钥环（macOS Keychain/Windows Credential/Linux SecretService）"""
        keyring.set_password(SecureStorage.SERVICE_NAME, f"jwt_{user_id}", jwt_token)

    @staticmethod
    def get_jwt(user_id: str) -> str | None:
        return keyring.get_password(SecureStorage.SERVICE_NAME, f"jwt_{user_id}")

    @staticmethod
    def delete_jwt(user_id: str) -> None:
        keyring.delete_password(SecureStorage.SERVICE_NAME, f"jwt_{user_id}")

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
