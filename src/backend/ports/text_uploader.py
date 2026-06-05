"""文本上传器协议。

定义文本上传的抽象接口，供集成层实现。
"""

from typing import Protocol


class TextUploader(Protocol):
    """文本上传器协议。

    用于将客户端文本无感上传到服务器。clientTextId 由服务端自动计算。

    实现类：
    - integration.text_uploader.TextUploader: 真实实现
    - integration.text_uploader.NoopTextUploader: 空实现
    """

    def upload(self, content: str, title: str, source_key: str) -> int | None:
        """上传文本内容到服务器。

        Args:
            content: 文本内容
            title: 文本标题
            source_key: 文本来源key

        Returns:
            int | None: 服务器分配的真实文本ID，失败返回 None
        """
        ...

    def upload_file(self, file_path: str, title: str, source_key: str) -> int | None:
        """上传文件到服务器（multipart/form-data）。

        Args:
            file_path: 本地文件路径
            title: 文本标题
            source_key: 文本来源key

        Returns:
            int | None: 服务器分配的真实文本ID，失败返回 None
        """
        ...
