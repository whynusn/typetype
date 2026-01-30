from Crypto.Cipher import AES
import base64
import json

# 密钥和初始向量 (Latin1 编码)
KEY = b'c9ec834c80f77237'
IV = b'db4d6bfde3057dca'


def zero_padding(data: bytes, block_size: int = 16) -> bytes:
    """
    ZeroPadding: 用零填充到块大小的倍数
    """
    padding_len = block_size - (len(data) % block_size)
    return data + b'\x00' * padding_len


def remove_zero_padding(data: bytes) -> bytes:
    """
    移除 ZeroPadding
    """
    return data.rstrip(b'\x00')


def encrypt(obj):
    """
    加密函数
    
    参数:
        obj: 字符串或可JSON序列化的对象
    
    返回:
        Base64 编码的加密字符串
    """
    # 将对象转换为字符串
    if isinstance(obj, str):
        raw = obj
    else:
        raw = json.dumps(obj)
    
    # Latin1 编码转换为字节
    raw_bytes = raw.encode('latin-1')
    
    # ZeroPadding 填充
    padded = zero_padding(raw_bytes)
    
    # 创建 AES cipher (CBC 模式)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    
    # 加密
    encrypted = cipher.encrypt(padded)
    
    # Base64 编码返回
    return base64.b64encode(encrypted).decode('utf-8')


def decrypt(encrypted_str):
    """
    解密函数
    
    参数:
        encrypted_str: Base64 编码的加密字符串
    
    返回:
        解密后的字符串
    """
    # Base64 解码
    encrypted = base64.b64decode(encrypted_str)
    
    # 创建 AES cipher (CBC 模式)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    
    # 解密
    decrypted = cipher.decrypt(encrypted)
    
    # 移除 ZeroPadding
    unpadded = remove_zero_padding(decrypted)
    
    # Latin1 解码为字符串
    return unpadded.decode('utf-8')


# ========== 测试示例 ==========
if __name__ == "__main__":
    # 测试加密字符串
    test_str = "Hello World!"
    encrypted = encrypt(test_str)
    print(f"原文: {test_str}")
    print(f"加密: {encrypted}")
    print(f"解密: {decrypt(encrypted)}")
    print()
    
    # 测试加密对象
    test_obj = {"name": "Alice", "age": 25, "city": "Beijing"}
    encrypted_obj = encrypt(test_obj)
    print(f"原文对象: {test_obj}")
    print(f"加密: {encrypted_obj}")
    print(f"解密: {decrypt(encrypted_obj)}")

    encrypted_str = "DA7WgIratat0hSZMwOeT5U1iurn+dP9j4RwVWg4Io8kdTmMo2GcXMtoHRzVUf8HT5CDtSYyivpnOWqeF/pxgW2LwYJLXivh864hJe+IEnAsbM5i4+5vfs65w4+O1xcHG7rXBZt2kak5keTkGetiH/9ITjBituDqolv7OVvrEK/wTcySGi2PdCtNkbMeDXzKhWKd2GQEPbpyO9b4EXp+MWzIQKuSEnWIci7uQ5vSeYqPayIcopU3xAypUX/ZQAb3Zgi3Ywqneerc45uEhT5ObSS3UJRY52u7VY6iowgZzc2bb7uXMzYUnPhPdaSxfdX4bsdEKB3DKJJXwrwk/cUNtxJOLeXySNpnuaMhgC3wulk3CUmSN1diCkUciqTbVfUlr3jCaQqDrwbuYK8s+AYMgQmC5EdkWyPgQazdBhWlRxvvkuiyy7ExpOB4Szxk9/t4Wp17U9tkP6LidP6lE52nxyDB7ElvMQ7m6ESzTW+1ktKcWvRT0OBIkW5BLJ6fp7wIkJ4CwIpYB4r2AfbDK+JxGG/rAtovTIUv4Gc78rdwZh3OIVVIyJ9to1XT7BCGNQKTHVRxdgfqS4Y/JGinO+/sF98T1e7UlT42bfX8DYafHE45RB0DC3n68ZftMRrN5rb1hLe2DVzEakmJxqhZVK4HiFZGFLCpwoiFmco/Q7g1M5MbGsEs/HHfP10IJk+HR2wpW35HyvoNl/heIj+VMQR1C6UCJrJav59zELrhYDnW67ANykf9FQQ6J8i2BQk2lquLDqCy+gmm/NEU4b+sc4EQ88KIPhiClNCzJhSDs6pK0y5VG5qDCQ3q3cLd1foMTuL65S4q5yL3HTQ+I8RFwrAjcWmhrTMCCc/H578QDMXr9IF1SXeyAUGo1javSGPR8b5dE29OsJFAxyJ0zz3QBT0j1/UWjVSG2rWYpcBDnNTtYnQNv3QX8vjDv9+oxgPQrvgzdt9UBa+lbHxd4DC4ptuKDhicugWgdzlKS40OLhtscBn8ZbbPErdsnY9NsEoD/lWVz2VIzTNTWz1ahKMo3XEsoej0sifWpbYDZyCUaWugnotjTvso0s802hODe3FjN1VrZk4HgCwz0hhkM+pxRtvfyZqREGjRT6bshVio6nHZ3L3vTXg0IlwzKy3c9xxiRQxmNneJ/kaQjd+q/hWWHuJZDWYpUzRb1aDO99G7bOpYBrPOIUNlVb0UxUOoOhoe8sn/fEyfOTJ2G3iSnP08Kk0cnjnxuMCuqcytvfSMSqsUop0oU1EQKNHcOK8u7bDij4Z3NxotBfKzlMDXeBSkGHsjkJxQRPd0OZfhh7gdb3hGbzDSbL4ey+abcbTHflfg3pYmSa4eiamS//iq8YPtaNcVXA+KFvigs3S0iTP9txtMgvOSEDMC1R48qKPVuqRZpHUFyCMvy8GpVNEeoaZ0BKERPJhaZa8Kt5w3Ii2ivzJcDnX0lAq8ITHoTGyS9+p26ECbspj0j3jGCLffN+CNu0trgqLZSQarnxUmUWq73EUoLCsnDKnkLLb0tGna4hynfvtSc2f6Z6B+Po2Q/Gnh/+z2Q1Wg18vZKCOt0Mu/sUDh+lDkUFAlYoBqFBFd9VWC/KHDPlbAK0l9p+ftARUDWc1jiDIvO+RtvNcsdmfYTAlk6JY50B/Oa3gImRKbQAjjb6GcV"

    print(f"解密: {decrypt(encrypted_str)}")

