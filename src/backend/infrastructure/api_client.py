from typing import Any

import httpx

from ..utils.logger import log_warning
from .network_errors import (
    NetworkDecodeError,
    NetworkError,
    NetworkRequestError,
    NetworkTimeoutError,
)


class ApiClient:
    """通用 HTTP 客户端，集中处理请求和异常。"""

    def __init__(self, timeout: float = 20.0):
        self._timeout = timeout
        timeout_config = httpx.Timeout(
            timeout=self._timeout, connect=min(self._timeout, 3.0)
        )
        self._client = httpx.Client(timeout=timeout_config)
        self._last_error: NetworkError | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[Any, Any] | None = None,
        json: dict[Any, Any] | None = None,
        data: dict[Any, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """
        发送通用 HTTP 请求并解析 JSON 响应。

        参数:
            method: HTTP 方法，如 GET/POST
            url: 请求地址
            params: 查询参数
            json: JSON 请求体
            data: 表单请求体
            headers: 请求头

        返回:
            解析后的 JSON 字典；失败时返回 None
        """
        try:
            response = self._client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                data=data,
                headers=headers,
            )
            result = response.json()
            self.clear_last_error()
            return result
        except httpx.TimeoutException as e:
            self._last_error = NetworkTimeoutError(str(e))
        except httpx.RequestError as e:
            self._last_error = NetworkRequestError(str(e))
        except ValueError as e:
            self._last_error = NetworkDecodeError(str(e))
        except Exception as e:
            self._last_error = NetworkError(str(e))

        log_warning(f"请求发生错误: {self._last_error}")
        return None

    @property
    def last_error(self) -> NetworkError | None:
        """返回最近一次请求错误，成功请求后会清空。"""
        return self._last_error

    def clear_last_error(self) -> None:
        """清除最近一次请求错误。"""
        self._last_error = None

    def get_json(
        self, url: str, params: dict[Any, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        发送 GET 请求并解析 JSON 响应。

        参数:
            url: 请求地址
            params: 查询参数

        返回:
            解析后的 JSON 字典；失败时返回 None
        """
        return self.request("GET", url, params=params)

    def post_json(self, url: str, payload: dict[Any, Any]) -> dict[str, Any] | None:
        """
        发送 POST JSON 请求。

        参数:
            url: 请求地址
            payload: JSON 请求体

        返回:
            解析后的 JSON 字典；失败时返回 None
        """
        return self.request("POST", url, json=payload)

    def close(self) -> None:
        """关闭 HTTP 客户端并释放连接资源。"""
        self._client.close()
