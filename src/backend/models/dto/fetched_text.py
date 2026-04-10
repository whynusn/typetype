"""获取的文本结果。

用于封装从服务器获取的文本数据，包含 id 和 content。
"""

from dataclasses import dataclass


@dataclass
class FetchedText:
    """从服务器获取的文本结果。"""

    content: str
    text_id: int | None = None
    title: str = ""
