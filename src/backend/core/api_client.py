from typing import Any

import httpx


class ApiClient:
    """通用 HTTP 客户端，集中处理请求和异常。"""

    def __init__(self, timeout: float = 20.0):
        self._timeout = timeout

    def post_json(self, url: str, payload: dict[Any, Any]) -> dict[str, Any] | None:
        """
        发送 POST JSON 请求。

        参数:
            url: 请求地址
            payload: JSON 请求体

        返回:
            解析后的 JSON 字典；失败时返回 None
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload)
            return response.json()
        except Exception as e:
            print(f"请求发生错误: {e}")
            return None
