from ...core.network_errors import (
    NetworkDecodeError,
    NetworkHttpStatusError,
    NetworkRequestError,
    NetworkTimeoutError,
)
from ..ports.clipboard import ClipboardReader
from ..ports.local_text_loader import LocalTextLoader
from ..ports.text_fetcher import TextFetcher


class TextUseCase:
    """文本加载相关用例。"""

    def __init__(
        self,
        text_fetcher: TextFetcher,
        clipboard: ClipboardReader,
        local_text_loader: LocalTextLoader,
    ):
        self._text_fetcher = text_fetcher
        self._clipboard = clipboard
        self._local_text_loader = local_text_loader

    def load_text_from_network(self, url: str) -> str | None:
        """从网络加载文本。"""
        try:
            return self._text_fetcher.fetch_text(url)
        except NetworkTimeoutError:
            return "加载文本失败：网络连接超时，请检查网络后重试"
        except NetworkRequestError:
            return "加载文本失败：网络请求失败，请检查网络连接"
        except NetworkDecodeError:
            return "加载文本失败：服务器响应异常，请稍后重试"
        except NetworkHttpStatusError as e:
            return f"加载文本失败：服务器状态异常({e.status_code})"
        except Exception as e:
            return f"加载文本失败：{str(e)}"

    def load_text_from_clipboard(self) -> str:
        """从剪贴板加载文本。"""
        new_text = ""

        try:
            new_text = self._clipboard.text()
            if not new_text:
                new_text = "当前剪贴板无文本内容"
        except Exception as e:
            new_text = f"从剪贴板加载文本失败: {str(e)}"

        return new_text

    def load_text_from_local(self, path: str) -> str | None:
        """从本地路径加载文本。"""
        try:
            return self._local_text_loader.load_text(path)
        except Exception:
            return "从本地文件加载文本失败"
