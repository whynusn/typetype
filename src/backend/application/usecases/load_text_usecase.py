from dataclasses import dataclass

from ...config.text_source_config import TextSourceEntry
from ...ports.clipboard import ClipboardReader
from ..gateways.text_source_gateway import TextSourceGateway


@dataclass(frozen=True)
class TextLoadPlan:
    """文本加载计划，持有已查找好的来源条目，避免重复查询。"""

    source_entry: TextSourceEntry


@dataclass
class LoadTextResult:
    success: bool
    text: str
    text_id: int | None = None
    source_label: str = ""
    source_key: str = ""
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
        source_entry = self._text_gateway.plan_load(source_key)
        return TextLoadPlan(source_entry=source_entry)

    def load(self, plan: TextLoadPlan) -> LoadTextResult:
        """根据执行计划加载文本。

        Args:
            plan: 预生成的加载计划

        Returns:
            LoadTextResult: 加载结果
        """
        success, fetched, error_message = self._text_gateway.load_from_plan(
            plan.source_entry
        )
        if not success or fetched is None:
            return LoadTextResult(success=False, text="", error_message=error_message)

        # 如果远程加载返回了具体标题，使用具体标题；否则使用来源标签
        result_title = fetched.title if fetched.title else plan.source_entry.label

        return LoadTextResult(
            success=True,
            text=fetched.content,
            text_id=fetched.text_id,
            source_label=result_title,
            source_key=plan.source_entry.key,
        )

    def load_from_clipboard(self) -> LoadTextResult:
        """从剪贴板加载文本。"""
        text = self._clipboard_reader.text()
        if not text:
            return LoadTextResult(
                success=False, text="", error_message="当前剪贴板无文本内容"
            )
        # 剪贴板文本不参与排行榜，text_id 为 None
        return LoadTextResult(
            success=True,
            text=text,
            text_id=None,
            source_label="剪贴板",
            source_key="",
        )

    def lookup_text_id(self, source_key: str, content: str) -> int | None:
        """按内容 hash 回查服务端 text_id（供异步回查使用）。

        通过 Gateway 的公开方法访问，不暴露 Gateway 引用。
        """
        return self._text_gateway.lookup_text_id(source_key, content)
