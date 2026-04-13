"""文本上传器协议。

定义文本上传的抽象接口，供集成层实现。
"""

from typing import Protocol


class TextUploader(Protocol):
    """文本上传器协议。

    用于将客户端文本无感上传到服务器。

    实现类：
    - integration.text_uploader.TextUploader: 真实实现
    - integration.text_uploader.NoopTextUploader: 空实现
    """

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
        ...
