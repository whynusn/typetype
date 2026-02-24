from typing import Protocol

from ...services.sai_wen_service import SaiWenService


class ClipboardReader(Protocol):
    """剪贴板读取协议，避免在用例层依赖 Qt。"""

    def text(self) -> str: ...


class TextUseCase:
    """文本加载相关用例。"""

    def __init__(self, sai_wen_service: SaiWenService, clipboard: ClipboardReader):
        self._sai_wen_service = sai_wen_service
        self._clipboard = clipboard

    def load_text_from_network(self, url: str) -> str | None:
        """从网络加载文本。"""
        try:
            return self._sai_wen_service.fetch_text(url)
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
            print(f"Error reading clipboard: {e}")

        return new_text
