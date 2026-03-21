"""Load Text Use Case - 文本加载业务流程编排。

协调 TextGateway 和 TextService，完成文本加载的完整流程。
"""

from dataclasses import dataclass

from ...infrastructure.network_errors import (
    NetworkDecodeError,
    NetworkHttpStatusError,
    NetworkRequestError,
    NetworkTimeoutError,
)
from ..ports.load_text_gateway import LoadTextGateway


@dataclass
class LoadTextResult:
    """文本加载结果。"""

    success: bool
    text: str
    error_message: str = ""


class LoadTextUseCase:
    """文本加载用例，编排加载流程。

    职责：
    - 根据 source_key 路由加载请求（network/local/clipboard）
    - 调用 TextGateway 执行加载
    - 处理异常并转换为用户友好的提示

    不负责：
    - 异步管理（由 Worker 负责）
    - UI 状态管理（由 Adapter 负责）
    - 信号发射（由 Adapter 负责）
    """

    def __init__(self, gateway: LoadTextGateway):
        self._gateway = gateway

    def load(self, source_key: str) -> LoadTextResult:
        """根据 source_key 加载文本。

        Args:
            source_key: 来源标识

        Returns:
            LoadTextResult: 加载结果
        """
        source = self._gateway.get_source(source_key)
        if not source:
            return LoadTextResult(
                success=False,
                text="",
                error_message=f"未知载文来源({source_key})",
            )

        if source.type == "local":
            return self._load_from_local(source.local_path)
        elif source.type == "network_direct":
            if not source.url:
                return LoadTextResult(
                    success=False,
                    text="",
                    error_message="网络来源缺少 URL",
                )
            return self._load_from_network(source.url, source.fetcher_key)
        elif source.type == "network_catalog":
            if not source.text_id:
                return LoadTextResult(
                    success=False,
                    text="",
                    error_message="文本库来源缺少 text_id",
                )
            return self._load_from_catalog(source.text_id)
        else:
            return LoadTextResult(
                success=False,
                text="",
                error_message=f"未知载文来源类型({source_key})",
            )

    def _load_from_network(self, url: str, fetcher_key: str | None) -> LoadTextResult:
        """从网络加载文本。"""
        try:
            text = self._gateway.fetch_from_network(url, fetcher_key)
            if text is None:
                return LoadTextResult(
                    success=False, text="", error_message="未获取到文本"
                )
            return LoadTextResult(success=True, text=text)
        except NetworkTimeoutError:
            return LoadTextResult(
                success=False,
                text="",
                error_message="网络连接超时，请检查网络后重试",
            )
        except NetworkRequestError:
            return LoadTextResult(
                success=False,
                text="",
                error_message="网络请求失败，请检查网络连接",
            )
        except NetworkDecodeError:
            return LoadTextResult(
                success=False,
                text="",
                error_message="服务器响应异常，请稍后重试",
            )
        except NetworkHttpStatusError as e:
            return LoadTextResult(
                success=False,
                text="",
                error_message=f"服务器状态异常({e.status_code})",
            )
        except Exception as e:
            return LoadTextResult(success=False, text="", error_message=str(e))

    def _load_from_catalog(self, text_id: str) -> LoadTextResult:
        """从文本库加载文本（根据 text_id）。"""
        try:
            text = self._gateway.fetch_from_catalog(text_id)
            if text is None:
                return LoadTextResult(
                    success=False, text="", error_message="未获取到文本"
                )
            return LoadTextResult(success=True, text=text)
        except Exception as e:
            return LoadTextResult(success=False, text="", error_message=str(e))

    def load_from_clipboard(self) -> LoadTextResult:
        """从剪贴板加载文本。"""
        try:
            text = self._gateway.fetch_from_clipboard()
            if not text:
                return LoadTextResult(
                    success=False,
                    text="",
                    error_message="当前剪贴板无文本内容",
                )
            return LoadTextResult(success=True, text=text)
        except Exception as e:
            return LoadTextResult(
                success=False,
                text="",
                error_message=f"从剪贴板加载失败: {str(e)}",
            )

    def _load_from_local(self, path: str | None) -> LoadTextResult:
        """从本地路径加载文本。"""
        if not path:
            return LoadTextResult(
                success=False, text="", error_message="本地来源缺少路径"
            )
        try:
            text = self._gateway.fetch_from_local(path)
            if text is None:
                return LoadTextResult(
                    success=False, text="", error_message="无法读取本地文章"
                )
            return LoadTextResult(success=True, text=text)
        except Exception:
            return LoadTextResult(
                success=False, text="", error_message="从本地文件加载失败"
            )
