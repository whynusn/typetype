class NetworkError(Exception):
    """网络错误基类。"""


class NetworkTimeoutError(NetworkError):
    """请求超时错误。"""


class NetworkHttpStatusError(NetworkError):
    """HTTP 状态码错误。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class NetworkDecodeError(NetworkError):
    """响应解析错误。"""


class NetworkRequestError(NetworkError):
    """请求发送错误。"""
