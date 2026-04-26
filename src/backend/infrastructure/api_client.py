from typing import Any
import time

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
        self._client = httpx.Client(timeout=timeout_config, trust_env=False)
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
        started_at = time.perf_counter()
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

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        log_warning(
            "请求发生错误: "
            f"{method.upper()} {url} params={params or {}} "
            f"elapsed={elapsed_ms}ms error={self._last_error}"
        )
        return None

    @property
    def last_error(self) -> NetworkError | None:
        """返回最近一次请求错误，成功请求后会清空。"""
        return self._last_error

    def clear_last_error(self) -> None:
        """清除最近一次请求错误。"""
        self._last_error = None

    def close(self) -> None:
        """关闭 HTTP 客户端并释放连接资源。"""
        self._client.close()
