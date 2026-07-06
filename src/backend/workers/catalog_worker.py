"""目录加载 Worker - 在后台线程执行网络请求。

优先使用 RegistryTextProvider 获取目录（Phase 3），fallback 到
LeaderboardGateway（兼容未配置开源文库的场景）。
"""

from typing import TYPE_CHECKING

from ..application.gateways.leaderboard_gateway import LeaderboardGateway
from .base_worker import BaseWorker

if TYPE_CHECKING:
    from ..integration.registry_text_provider import RegistryTextProvider


class CatalogWorker(BaseWorker):
    """目录加载 Worker - 在后台线程执行网络请求。"""

    def __init__(
        self,
        leaderboard_gateway: LeaderboardGateway,
        registry_provider: "RegistryTextProvider | None" = None,
    ):
        self._leaderboard_gateway = leaderboard_gateway
        self._registry_provider = registry_provider
        super().__init__(task=self._fetch_catalog, error_prefix="加载目录失败")

    def _fetch_catalog(self) -> list[dict]:
        """获取文本来源目录。

        优先使用 RegistryTextProvider.get_catalog()（Phase 3），
        fallback 到 LeaderboardGateway（兼容无开源文库场景）。
        """
        if self._registry_provider is not None:
            catalog = self._registry_provider.get_catalog()
            if catalog:
                return [
                    {
                        "id": item.id,
                        "sourceKey": item.source_key,
                        "label": item.label,
                        "description": item.description,
                        "charCount": item.charCount,
                    }
                    for item in catalog
                ]

        # Fallback: 使用 LeaderboardGateway（网络 API）
        catalog = self._leaderboard_gateway.get_catalog()
        if catalog is None:
            raise Exception("无法获取文本来源目录")
        return catalog
