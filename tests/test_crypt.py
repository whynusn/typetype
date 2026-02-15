"""
加密解密功能测试
"""

from src.backend.crypt import decrypt, encrypt, remove_zero_padding, zero_padding


class TestPadding:
    """测试填充功能"""

    def test_zero_padding_empty(self):
        """测试空字符串填充"""
        result = zero_padding(b"", block_size=16)
        assert result == b"\x00" * 16

    def test_zero_padding_exact_block(self):
        """测试恰好是块大小的数据"""
        data = b"a" * 16
        result = zero_padding(data, block_size=16)
        assert result == data + b"\x00" * 16

    def test_zero_padding_partial_block(self):
        """测试部分块填充"""
        data = b"hello"
        result = zero_padding(data, block_size=16)
        assert result == data + b"\x00" * 11

    def test_remove_zero_padding(self):
        """测试移除填充"""
        data = b"hello\x00\x00\x00"
        result = remove_zero_padding(data)
        assert result == b"hello"

    def test_padding_roundtrip(self):
        """测试填充和移除的往返"""
        original = b"test data"
        padded = zero_padding(original, block_size=16)
        unpadded = remove_zero_padding(padded)
        assert unpadded == original


class TestEncryptDecrypt:
    """测试加密解密功能"""

    def test_encrypt_string(self):
        """测试字符串加密"""
        test_str = "Hello World!"
        encrypted = encrypt(test_str)
        assert isinstance(encrypted, str)
        assert encrypted != test_str

    def test_encrypt_dict(self):
        """测试字典加密"""
        test_dict = {"name": "Alice", "age": 25}
        encrypted = encrypt(test_dict)
        assert isinstance(encrypted, str)

    def test_decrypt_roundtrip_string(self):
        """测试字符串加密解密往返"""
        original = "Hello World!"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_roundtrip_dict(self):
        """测试字典加密解密往返"""
        original = {"key": "value", "number": 42}
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == '{"key": "value", "number": 42}'

    def test_encrypt_special_chars(self):
        """测试特殊字符加密（仅 ASCII）"""
        test_str = "Hello! @#$%^&*()"
        encrypted = encrypt(test_str)
        decrypted = decrypt(encrypted)
        assert decrypted == test_str

    def test_encrypt_empty_string(self):
        """测试空字符串加密"""
        test_str = ""
        encrypted = encrypt(test_str)
        decrypted = decrypt(encrypted)
        assert decrypted == test_str

    def test_encrypt_long_string(self):
        """测试长字符串加密"""
        test_str = "a" * 1000
        encrypted = encrypt(test_str)
        decrypted = decrypt(encrypted)
        assert decrypted == test_str
