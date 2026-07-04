"""文本来源网关 - 配置解析 + Port 适配。

职责：
- 读取文本来源配置（持有 RuntimeConfig）
- 根据 Loader 决定路由到哪个 Provider
- 调用相应的 Port（TextProvider / LocalTextLoader）

不负责：
- Qt 信号、UI 状态
- 业务流程编排（由 LoadTextUseCase 负责）
"""

from typing import TYPE_CHECKING

from ...config.runtime_config import RuntimeConfig
from ...config.text_source_config import Loader
from ...models.dto.fetched_text import FetchedText
from ...ports.local_text_loader import LocalTextLoader
from ...ports.text_provider import TextProvider
from ...utils.logger import log_info
from ...utils.text_id import text_id_from_content

if TYPE_CHECKING:
    from ...config.text_source_config import TextSourceEntry


class TextSourceGateway:
    """文本来源网关，负责配置查询和 Port 适配。"""

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        text_provider: TextProvider,
        local_text_loader: LocalTextLoader,
        registry_provider: TextProvider | None = None,
    ):
        self._runtime_config = runtime_config
        self._text_provider = text_provider
        self._local_text_loader = local_text_loader
        self._registry_provider = registry_provider

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

        路由决策：按 TextSourceEntry.loader 决定走哪个 Provider，
        与排行榜行为（leaderboard_mode）解耦。
        """
        if source.loader == Loader.REMOTE_API:
            return self._load_from_network(source.key)

        if source.loader == Loader.REGISTRY:
            if not self._registry_provider:
                return False, None, "注册表文本源未配置"
            fetched = self._registry_provider.fetch_text_by_key(source.key)
            if fetched is None:
                return False, None, f"无法获取注册表文本({source.key})"
            return True, fetched, ""

        # LOCAL_FILE：读本地文件
        return self._load_from_local(source.local_path, source.label, source.key)

    def _load_from_local(
        self, path: str | None, label: str = "", source_key: str = ""
    ) -> tuple[bool, FetchedText | None, str]:
        """从本地文件加载文本。

        只读本地文件，立即返回。text_id 由调用方通过后台线程异步回查。
        """
        if not path:
            return False, None, "本地来源缺少路径"
        text = self._local_text_loader.load_text(path)
        if text is None:
            return False, None, "无法读取本地文件"
        return True, FetchedText(content=text, text_id=None), ""

    def lookup_text_id(self, source_key: str, content: str) -> int | None:
        """通过 clientTextId 异步回查服务端文本 ID（供后台线程调用）。"""
        return self._lookup_server_text_id(source_key, content)

    def _lookup_server_text_id(self, source_key: str, content: str) -> int | None:
        """通过 clientTextId 回查服务端文本 ID。

        本地内容与服务端一致时返回服务端 ID，不一致（用户修改过）时返回 None。
        服务端对不存在的 sourceKey 会回退到 "custom"，因此需尝试两次。
        hash 不匹配说明内容有差异，返回 None 走纯练习模式（不提交成绩）。
        """
        if not source_key:
            return None
        # 先用实际 sourceKey 查，再用 "custom" 查（服务端对未知来源的回退策略）
        for key in [source_key, "custom"]:
            try:
                client_text_id = text_id_from_content(key, content)
                fetched = self._text_provider.fetch_text_by_client_id(client_text_id)
                if fetched and fetched.text_id is not None:
                    log_info(
                        f"[TextSourceGateway] hash lookup matched: key='{key}' text_id={fetched.text_id}"
                    )
                    return fetched.text_id
            except Exception:
                pass
        return None

    def _load_from_network(
        self, source_key: str
    ) -> tuple[bool, FetchedText | None, str]:
        """从网络加载文本。"""
        fetched = self._text_provider.fetch_text_by_key(source_key)
        if fetched is None:
            return False, None, f"无法获取网络文本({source_key})"

        # 网络来源：直接使用服务端返回的 text_id
        return True, fetched, ""
