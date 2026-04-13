"""文本来源网关 - 配置解析 + Port 适配。

职责：
- 读取文本来源配置（持有 RuntimeConfig）
- 根据 source_key 决定走本地还是网络
- 调用相应的 Port（TextProvider / LocalTextLoader）

不负责：
- Qt 信号、UI 状态
- 业务流程编排（由 LoadTextUseCase 负责）
"""

from typing import TYPE_CHECKING

from ...models.dto.fetched_text import FetchedText
from ...config.runtime_config import RuntimeConfig
from ...ports.local_text_loader import LocalTextLoader
from ...ports.text_provider import TextProvider

if TYPE_CHECKING:
    from ...config.text_source_config import TextSourceEntry


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

    def plan_load(self, source_key: str) -> "TextSourceEntry":
        """规划加载：查找来源。

        只执行一次 get_text_source 查询，得到的结果会缓存在 TextLoadPlan 中供后续加载使用。
        """
        source = self._runtime_config.get_text_source(source_key)
        if not source:
            raise ValueError(f"未知文本来源({source_key})")
        return source

    def load_from_plan(
        self, source: "TextSourceEntry"
    ) -> tuple[bool, FetchedText | None, str]:
        """根据已规划的来源条目加载文本。

        不需要再次查找 source，直接使用已找到的条目。

        Returns:
            tuple[bool, FetchedText | None, str]: (成功, 文本对象, 错误信息)
        """
        if source.local_path:
            return self._load_from_local(source.local_path, source.label)

        # 网络来源
        return self._load_from_network(source.key)

    def _load_from_local(
        self, path: str | None, label: str = ""
    ) -> tuple[bool, FetchedText | None, str]:
        """从本地文件加载文本。"""
        if not path:
            return False, None, "本地来源缺少路径"
        text = self._local_text_loader.load_text(path)
        if text is None:
            return False, None, "无法读取本地文件"
        # 本地文本不参与排行榜，text_id 为 None
        return True, FetchedText(content=text, text_id=None), ""

    def _load_from_network(
        self, source_key: str
    ) -> tuple[bool, FetchedText | None, str]:
        """从网络加载文本。"""
        fetched = self._text_provider.fetch_text_by_key(source_key)
        if fetched is None:
            return False, None, f"无法获取网络文本({source_key})"

        # 网络来源：直接使用服务端返回的 text_id
        return True, fetched, ""
