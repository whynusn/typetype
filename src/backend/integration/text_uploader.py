"""文本上传器 - 无感上传用户文本到服务器。"""

from collections.abc import Callable
from pathlib import Path

from ..infrastructure.api_client import ApiClient
from ..utils.logger import log_warning


class TextUploader:
    """无感上传文本到服务器。"""

    def __init__(
        self,
        api_client: ApiClient,
        upload_url: str,
        token_provider: Callable[[], str] = lambda: "",
    ):
        self._api_client = api_client
        self._upload_url = upload_url
        self._token_provider = token_provider

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 及其派生的上传 URL。"""
        new_base_url = new_base_url.rstrip("/")
        self._upload_url = f"{new_base_url}/api/v1/texts/upload"

    def upload(self, content: str, title: str, source_key: str) -> int | None:
        """上传文本内容到服务器（JSON body）。

        Args:
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
            f"[TextUploader] 上传文本：title={title}, source_key={source_key}, length={len(content)}"
        )
        payload = {
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

        return self._parse_upload_response(data)

    def upload_file(self, file_path: str, title: str, source_key: str) -> int | None:
        """上传文件到服务器（multipart/form-data）。

        文件内容由 httpx 分块读取传输，不会全量加载到内存。

        Args:
            file_path: 本地文件路径
            title: 文本标题
            source_key: 文本来源key

        Returns:
            int | None: 服务器分配的真实文本ID，失败返回 None
        """
        token = self._token_provider()
        if not token:
            log_warning("[TextUploader] 无法上传：未登录")
            return None

        path = Path(file_path)
        if not path.exists():
            log_warning(f"[TextUploader] 文件不存在：{file_path}")
            return None

        file_size = path.stat().st_size
        log_warning(
            f"[TextUploader] 上传文件：title={title}, source_key={source_key}, size={file_size}"
        )

        headers = {"Authorization": f"Bearer {token}"}

        try:
            with open(file_path, "rb") as f:
                files = {"file": (path.name, f, "text/plain")}
                form_data = {
                    "title": title,
                    "sourceKey": source_key,
                }
                data = self._api_client.request(
                    "POST",
                    self._upload_url,
                    files=files,
                    data=form_data,
                    headers=headers,
                )
                return self._parse_upload_response(data)
        except Exception as e:
            log_warning(f"[TextUploader] 文件上传失败：{e}")
            return None

    def _parse_upload_response(self, data: dict | None) -> int | None:
        """解析上传响应。"""
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

    def upload(self, content: str, title: str, source_key: str) -> int | None:
        return None

    def upload_file(self, file_path: str, title: str, source_key: str) -> int | None:
        return None
