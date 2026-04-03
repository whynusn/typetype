from dataclasses import dataclass
from typing import Literal

from ..gateways.text_source_gateway import TextSourceGateway
from ..ports.clipboard import ClipboardReader


@dataclass(frozen=True)
class TextLoadPlan:
    execution_mode: Literal["sync", "async"]


@dataclass
class LoadTextResult:
    success: bool
    text: str
    error_message: str = ""


class LoadTextUseCase:
    """文本加载用例 - 业务流程编排。

    职责：
    - 文本加载的业务编排入口
    - 剪贴板加载逻辑

    不负责：
    - 配置查询与路由决策（由 TextSourceGateway 负责）
    - Qt 信号、UI 状态
    """

    def __init__(
        self,
        text_gateway: TextSourceGateway,
        clipboard_reader: ClipboardReader,
    ):
        self._text_gateway = text_gateway
        self._clipboard_reader = clipboard_reader

    def plan_load(self, source_key: str) -> TextLoadPlan:
        """返回文本加载的执行计划。"""
        return TextLoadPlan(
            execution_mode=self._text_gateway.get_execution_mode(source_key)
        )

    def load(self, source_key: str) -> LoadTextResult:
        """根据 source_key 加载文本。

        Args:
            source_key: 文本来源键

        Returns:
            LoadTextResult: 加载结果
        """
        success, text, error_message = self._text_gateway.load_text_by_key(source_key)
        return LoadTextResult(
            success=success, text=text or "", error_message=error_message
        )

    def load_from_clipboard(self) -> LoadTextResult:
        """从剪贴板加载文本。"""
        text = self._clipboard_reader.text()
        if not text:
            return LoadTextResult(
                success=False, text="", error_message="当前剪贴板无文本内容"
            )
        return LoadTextResult(success=True, text=text)
