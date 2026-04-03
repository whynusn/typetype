"""文本来源网关 - 配置解析 + Port 适配。

职责：
- 读取文本来源配置（持有 RuntimeConfig）
- 根据 source_key 决定走本地还是网络
- 调用相应的 Port（TextProvider / LocalTextLoader）

不负责：
- Qt 信号、UI 状态
- 业务流程编排（由 LoadTextUseCase 负责）
"""

from typing import Literal
from typing import TYPE_CHECKING

from ...config.runtime_config import RuntimeConfig
from ..ports.local_text_loader import LocalTextLoader
from ..ports.text_provider import TextProvider

if TYPE_CHECKING:
    pass


class TextSourceGateway:
    """文本来源网关，负责配置查询和 Port 适配。"""

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        text_provider: TextProvider,
        local_text_loader: LocalTextLoader,
    ):
        self._runtime_config = runtime_config
        self._text_provider = text_provider
        self._local_text_loader = local_text_loader

    def get_execution_mode(self, source_key: str) -> Literal["sync", "async"]:
        """根据 source_key 返回 Presentation 应执行的加载模式。"""
        source = self._runtime_config.get_text_source(source_key)
        if not source:
            raise ValueError(f"未知文本来源({source_key})")
        return "sync" if source.local_path else "async"

    def load_text_by_key(self, source_key: str) -> tuple[bool, str | None, str]:
        """根据 source_key 加载文本。

        Args:
            source_key: 文本来源键

        Returns:
            tuple: (success, text, error_message)
                success: 是否加载成功
                text: 文本内容（成功时）或 None
                error_message: 错误信息（失败时）
        """
        source = self._runtime_config.get_text_source(source_key)
        if not source:
            return False, None, f"未知文本来源({source_key})"

        if source.local_path:
            return self._load_from_local(source.local_path)

        # 网络来源
        return self._load_from_network(source.key)

    def _load_from_local(self, path: str | None) -> tuple[bool, str | None, str]:
        """从本地文件加载文本。"""
        if not path:
            return False, None, "本地来源缺少路径"
        text = self._local_text_loader.load_text(path)
        if text is None:
            return False, None, "无法读取本地文件"
        return True, text, ""

    def _load_from_network(self, source_key: str) -> tuple[bool, str | None, str]:
        """从网络加载文本。"""
        text = self._text_provider.fetch_text_by_key(source_key)
        if text is None:
            return False, None, f"无法获取网络文本({source_key})"
        return True, text, ""
