import hashlib


def text_id_from_content(label: str, content: str) -> int:
    """将 label 和文本内容联合 hash 为 10 位以内的正整数。

    用于防止用户修改本地文件后仍使用相同 text_id。
    """
    combined = f"{label}:{content}"
    h = hashlib.sha256(combined.encode("utf-8"))
    return int(h.hexdigest()[:8], 16) % (10**9)
