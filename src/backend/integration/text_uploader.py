"""文本上传器 - 无感上传用户文本到服务器。"""

from collections.abc import Callable

from ..infrastructure.api_client import ApiClient
from ..utils.logger import log_warning


class TextUploader:
    """异步无感上传文本到服务器。"""

    def __init__(
        self,
        api_client: ApiClient,
        upload_url: str,
        token_provider: Callable[[], str] = lambda: "",
    ):
        self._api_client = api_client
        self._upload_url = upload_url
        self._token_provider = token_provider

    def upload(
        self, client_text_id: int, content: str, title: str, source_key: str
    ) -> int | None:
        """上传文本到服务器。

        Args:
            client_text_id: 客户端计算的文本ID（hash）
            content: 文本内容
            title: 文本标题
            source_key: 文本来源key

        Returns:
            int | None: 服务器分配的真实文本ID，失败返回 None
        """
        token = self._token_provider()
        if not token:
            log_warning("[TextUploader] 无法上传：未登录")
            return None

        log_warning(
            f"[TextUploader] 开始上传文本：client_text_id={client_text_id}, title={title}, source_key={source_key}, length={len(content)}"
        )
        payload = {
            "clientTextId": client_text_id,
            "content": content,
            "title": title,
            "sourceKey": source_key,
        }
        headers = {"Authorization": f"Bearer {token}"}

        data = self._api_client.request(
            "POST",
            self._upload_url,
            json=payload,
            headers=headers,
        )

        if data is None or data.get("code") != 200:
            log_warning(
                f"[TextUploader] 上传失败：code={data.get('code') if data else 'None'}"
            )
            return None
        result = data.get("data")
        if result and isinstance(result, dict):
            real_id = result.get("id")
            log_warning(f"[TextUploader] 上传成功：real_text_id={real_id}")
            return real_id
        log_warning("[TextUploader] 上传失败：响应数据格式错误")
        return None


class NoopTextUploader:
    """空实现，用于禁用上传场景。"""

    def upload(
        self, client_text_id: int, content: str, title: str, source_key: str
    ) -> int | None:
        return None
