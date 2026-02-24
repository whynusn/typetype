"""TextUseCase 测试。"""

from src.backend.application.usecases.text_usecase import TextUseCase


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

    def __init__(self, result="text", should_raise=False):
        self._result = result
        self._should_raise = should_raise

    def fetch_text(self, _url):
        if self._should_raise:
            raise RuntimeError("network error")
        return self._result


def test_load_text_from_network_success():
    """网络加载成功应返回文本。"""
    usecase = TextUseCase(DummySaiWenService(result="abc"), DummyClipboard())
    assert usecase.load_text_from_network("https://example.com") == "abc"


def test_load_text_from_network_error():
    """网络异常应返回失败文案。"""
    usecase = TextUseCase(DummySaiWenService(should_raise=True), DummyClipboard())
    assert (
        usecase.load_text_from_network("https://example.com")
        == "加载文本失败：network error"
    )


def test_load_text_from_clipboard_with_text():
    """剪贴板有内容时应直接返回。"""
    usecase = TextUseCase(DummySaiWenService(), DummyClipboard(value="clip"))
    assert usecase.load_text_from_clipboard() == "clip"


def test_load_text_from_clipboard_empty():
    """剪贴板为空时应返回提示文案。"""
    usecase = TextUseCase(DummySaiWenService(), DummyClipboard(value=""))
    assert usecase.load_text_from_clipboard() == "当前剪贴板无文本内容"


def test_load_text_from_clipboard_error():
    """剪贴板异常时应回退为空字符串。"""
    usecase = TextUseCase(DummySaiWenService(), DummyClipboard(should_raise=True))
    assert usecase.load_text_from_clipboard() == ""
