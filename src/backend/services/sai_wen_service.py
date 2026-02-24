import time
from typing import Any

from ..core.api_client import ApiClient
from ..security import crypt


class SaiWenService:
    """赛文文本服务，封装请求构造与响应解析。"""

    def __init__(self, api_client: ApiClient | None = None):
        self._api_client = api_client or ApiClient(timeout=20.0)

    def fetch_text(self, url: str) -> str | None:
        """
        从赛文接口获取文本。

        参数:
            url: 赛文接口地址

        返回:
            提取后的文本内容；失败时返回 None
        """
        payload = self._build_payload()
        response_data = self._api_client.post_json(url, payload)
        if response_data is None:
            return None
        return self._extract_text(response_data)

    def _build_payload(self) -> dict[Any, Any]:
        """构造并加密请求体。"""
        data = {
            "competitionType": 0,
            "snumflag": "1",
            "from": "web",
            "timestamp": int(time.time()),
            "version": "v2.1.5",
            "subversions": 17108,
        }
        cipher = crypt.encrypt(data)
        return {0: cipher[1:]}

    @staticmethod
    def _extract_text(response_data: dict[str, Any]) -> str:
        """解析接口返回中的文本字段。"""
        msg = response_data.get("msg")

        if isinstance(msg, str):
            return msg

        if isinstance(msg, dict):
            if "content" in msg:
                return msg["content"]
            if "0" in msg:
                return msg["0"]

        return str(msg) if msg else ""
