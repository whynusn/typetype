"""LoadTextUseCase 测试。"""

from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.models.text_source import TextSource
from src.backend.infrastructure.network_errors import (
    NetworkTimeoutError,
)


class DummyTextGateway:
    def __init__(self, sources=None, network_result=None, network_error=None):
        self._sources = sources or {}
        self._network_result = network_result
        self._network_error = network_error

    def get_source(self, source_key):
        return self._sources.get(source_key)

    def fetch_from_network(self, url, fetcher_key=None):
        if self._network_error:
            raise self._network_error
        return self._network_result

    def fetch_from_catalog(self, text_id):
        return self._network_result

    def fetch_from_clipboard(self):
        return "clipboard text"

    def fetch_from_local(self, path):
        return "local text"


def test_load_network_success():
    """网络加载成功应返回成功结果。"""
    gateway = DummyTextGateway(
        sources={
            "test": TextSource(
                key="test",
                label="Test Network",
                type="network_direct",
                url="https://example.com",
                fetcher_key="default",
            )
        },
        network_result="abc",
    )
    usecase = LoadTextUseCase(gateway=gateway)
    result = usecase.load("test")
    assert result.success
    assert result.text == "abc"


def test_load_network_timeout_error():
    """超时异常应返回专用提示。"""
    gateway = DummyTextGateway(
        sources={
            "test": TextSource(
                key="test",
                label="Test Network",
                type="network_direct",
                url="https://example.com",
                fetcher_key="default",
            )
        },
        network_error=NetworkTimeoutError("timeout"),
    )
    usecase = LoadTextUseCase(gateway=gateway)
    result = usecase.load("test")
    assert not result.success
    assert "网络连接超时" in result.error_message


def test_load_unknown_source():
    """未知来源应返回失败。"""
    gateway = DummyTextGateway(sources={})
    usecase = LoadTextUseCase(gateway=gateway)
    result = usecase.load("unknown")
    assert not result.success
    assert "未知载文来源" in result.error_message


def test_load_from_clipboard():
    """从剪贴板加载应成功。"""
    gateway = DummyTextGateway()
    usecase = LoadTextUseCase(gateway=gateway)
    result = usecase.load_from_clipboard()
    assert result.success
    assert result.text == "clipboard text"


def test_load_local_success():
    """本地加载成功应返回文本。"""
    gateway = DummyTextGateway(
        sources={
            "test": TextSource(
                key="test",
                label="Test Local",
                type="local",
                local_path="/path/to/file.txt",
            )
        }
    )
    usecase = LoadTextUseCase(gateway=gateway)
    result = usecase.load("test")
    assert result.success
    assert result.text == "local text"
