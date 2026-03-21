"""Text Gateway - Port 适配 + 异常转换。

封装 Port 调用，提供统一的文本加载接口。
"""

from ...config.runtime_config import RuntimeConfig
from ...models.text_source import TextSource
from ..ports.clipboard import ClipboardReader
from ..ports.local_text_loader import LocalTextLoader
from ..ports.text_catalog_fetcher import TextCatalogFetcher
from ..ports.text_fetcher import TextFetcher


class TextGateway:
    """文本加载网关，封装 Port 调用和配置查询。

    职责：
    - 根据 source_key 查询来源配置
    - 调用 TextFetcher 获取网络文本（支持多个 fetcher 共存）
    - 调用 LocalTextLoader 获取本地文本
    - 调用 Clipboard 获取剪贴板文本
    - 获取文本目录（从后端）

    不负责：
    - 业务流程编排（由 UseCase 负责）
    - 异常转换（由 LoadTextUseCase 负责）
    - 异步管理（由 Worker 负责）
    """

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        text_fetchers: dict[str, TextFetcher],
        clipboard: ClipboardReader,
        local_text_loader: LocalTextLoader,
        text_catalog_fetcher: TextCatalogFetcher | None = None,
    ):
        self._runtime_config = runtime_config
        self._text_fetchers = text_fetchers
        self._clipboard = clipboard
        self._local_text_loader = local_text_loader
        self._text_catalog_fetcher = text_catalog_fetcher

    def get_source(self, source_key: str) -> TextSource | None:
        """根据 source_key 获取来源配置。"""
        return self._runtime_config.get_text_source(source_key)

    def get_source_options(self) -> list[dict[str, str]]:
        """获取 UI 可选的来源列表。"""
        return self._runtime_config.get_text_source_options()

    def get_default_source_key(self) -> str:
        """获取默认来源 key。"""
        return self._runtime_config.default_text_source_key

    def _get_fetcher(self, fetcher_key: str | None) -> TextFetcher:
        """获取指定的 TextFetcher。"""
        if fetcher_key and fetcher_key in self._text_fetchers:
            return self._text_fetchers[fetcher_key]
        if self._text_fetchers:
            return next(iter(self._text_fetchers.values()))
        raise ValueError("没有可用的 TextFetcher")

    def fetch_from_network(
        self, url: str, fetcher_key: str | None = None
    ) -> str | None:
        """从网络加载文本（直接 URL）。"""
        fetcher = self._get_fetcher(fetcher_key)
        return fetcher.fetch_text(url)

    def fetch_from_catalog(self, text_id: str) -> str | None:
        """从文本库获取文本（根据 text_id）。"""
        if not text_id or self._text_catalog_fetcher is None:
            return None
        return self._text_catalog_fetcher.fetch_text_by_id(text_id)

    def fetch_from_clipboard(self) -> str:
        """从剪贴板加载文本。"""
        text = self._clipboard.text()
        return text if text else ""

    def fetch_from_local(self, path: str) -> str | None:
        """从本地路径加载文本。"""
        return self._local_text_loader.load_text(path)
