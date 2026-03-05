"""TextUseCase 测试。"""

from src.backend.application.usecases.text_usecase import TextUseCase
from src.backend.core.network_errors import (
    NetworkDecodeError,
    NetworkHttpStatusError,
    NetworkRequestError,
    NetworkTimeoutError,
)


class DummyClipboard:
    """用于测试剪贴板读取。"""

    def __init__(self, value="", should_raise=False):
        self._value = value
        self._should_raise = should_raise

    def text(self):
        if self._should_raise:
            raise RuntimeError("clipboard error")
        return self._value


class DummySaiWenService:
    """用于测试赛文服务调用。"""

    def __init__(self, result="text", should_raise=False, exception=None):
        self._result = result
        self._should_raise = should_raise
        self._exception = exception

    def fetch_text(self, _url):
        if self._exception is not None:
            raise self._exception
        if self._should_raise:
            raise RuntimeError("network error")
        return self._result


class DummyLocalTextLoader:
    """用于测试本地文本加载。"""

    def __init__(self, value="local text", should_raise=False):
        self._value = value
        self._should_raise = should_raise

    def load_text(self, _path):
        if self._should_raise:
            raise RuntimeError("local load error")
        return self._value


def test_load_text_from_network_success():
    """网络加载成功应返回文本。"""
    usecase = TextUseCase(
        DummySaiWenService(result="abc"),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert usecase.load_text_from_network("https://example.com") == "abc"


def test_load_text_from_network_error():
    """网络异常应返回失败文案。"""
    usecase = TextUseCase(
        DummySaiWenService(should_raise=True),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：network error"
    )


def test_load_text_from_network_timeout_error():
    """超时异常应返回专用提示。"""
    usecase = TextUseCase(
        DummySaiWenService(exception=NetworkTimeoutError("timeout")),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：网络连接超时，请检查网络后重试"
    )


def test_load_text_from_network_request_error():
    """请求异常应返回专用提示。"""
    usecase = TextUseCase(
        DummySaiWenService(exception=NetworkRequestError("request failed")),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：网络请求失败，请检查网络连接"
    )


def test_load_text_from_network_decode_error():
    """解析异常应返回专用提示。"""
    usecase = TextUseCase(
        DummySaiWenService(exception=NetworkDecodeError("bad json")),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：服务器响应异常，请稍后重试"
    )


def test_load_text_from_network_http_status_error():
    """状态码异常应返回状态码提示。"""
    usecase = TextUseCase(
        DummySaiWenService(
            exception=NetworkHttpStatusError(503, "service unavailable")
        ),
        DummyClipboard(),
        DummyLocalTextLoader(),
    )
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：服务器状态异常(503)"
    )


def test_load_text_from_clipboard_with_text():
    """剪贴板有内容时应直接返回。"""
    usecase = TextUseCase(
        DummySaiWenService(),
        DummyClipboard(value="clip"),
        DummyLocalTextLoader(),
    )
    assert usecase.load_text_from_clipboard() == "clip"


def test_load_text_from_clipboard_empty():
    """剪贴板为空时应返回提示文案。"""
    usecase = TextUseCase(
        DummySaiWenService(),
        DummyClipboard(value=""),
        DummyLocalTextLoader(),
    )
    assert usecase.load_text_from_clipboard() == "当前剪贴板无文本内容"


def test_load_text_from_clipboard_error():
    """剪贴板异常时应返回失败文案。"""
    usecase = TextUseCase(
        DummySaiWenService(),
        DummyClipboard(should_raise=True),
        DummyLocalTextLoader(),
    )
    assert usecase.load_text_from_clipboard() == "从剪贴板加载文本失败: clipboard error"


def test_load_text_from_local_success():
    """本地载文成功应返回文本。"""
    usecase = TextUseCase(
        DummySaiWenService(),
        DummyClipboard(),
        DummyLocalTextLoader(value="本地文章"),
    )
    assert usecase.load_text_from_local("./resources/texts/demo.txt") == "本地文章"


def test_load_text_from_local_error():
    """本地载文异常应返回 None。"""
    usecase = TextUseCase(
        DummySaiWenService(),
        DummyClipboard(),
        DummyLocalTextLoader(should_raise=True),
    )
    assert (
        usecase.load_text_from_local("./resources/texts/demo.txt")
        == "从本地文件加载文本失败"
    )
