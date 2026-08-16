"""文本来源网关 - 配置解析 + Port 适配。

职责：
- 读取文本来源配置（持有 RuntimeConfig）
- 路由本地文件加载（Loader.LOCAL_FILE，唯一剩余 Loader）
- 调用 LocalTextLoader 端口

不负责：
- Qt 信号、UI 状态
- 业务流程编排（由 LoadTextUseCase 负责）
- 远程文本拉取 / text_id hash 回查（typetype-server 耦合已移除，ADR-013）
"""

from typing import TYPE_CHECKING

from ...config.runtime_config import RuntimeConfig
from ...models.dto.fetched_text import FetchedText
from ...ports.local_text_loader import LocalTextLoader

if TYPE_CHECKING:
    from ...config.text_source_config import TextSourceEntry


class TextSourceGateway:
    """文本来源网关，负责配置查询和 Port 适配。"""

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        local_text_loader: LocalTextLoader,
    ):
        self._runtime_config = runtime_config
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

        客户端空壳化后仅剩本地文件来源：读本地文件立即返回，text_id 恒为 None。
        """
        return self._load_from_local(source.local_path, source.label, source.key)

    def _load_from_local(
        self, path: str | None, label: str = "", source_key: str = ""
    ) -> tuple[bool, FetchedText | None, str]:
        """从本地文件加载文本。"""
        if not path:
            return False, None, "本地来源缺少路径"
        text = self._local_text_loader.load_text(path)
        if text is None:
            return False, None, "无法读取本地文件"
        return True, FetchedText(content=text, text_id=None), ""
