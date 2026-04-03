from src.backend.application.usecases.load_text_usecase import LoadTextUseCase


class DummyTextSourceGateway:
    def __init__(self):
        self._success = True
        self._text = ""
        self._error_message = ""
        self._execution_mode = "sync"

    def set_success_result(self, text: str):
        self._success = True
        self._text = text

    def set_failure_result(self, error_message: str):
        self._success = False
        self._error_message = error_message

    def set_execution_mode(self, execution_mode: str):
        self._execution_mode = execution_mode

    def get_execution_mode(self, source_key: str):
        return self._execution_mode

    def load_text_by_key(self, source_key: str):
        if self._success:
            return (True, self._text, "")
        return (False, None, self._error_message)


class DummyClipboardReader:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


def test_load_success():
    """测试成功加载文本。"""
    gateway = DummyTextSourceGateway()
    gateway.set_success_result("test text")

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    result = usecase.load("any_key")
    assert result.success
    assert result.text == "test text"


def test_plan_load_returns_gateway_execution_mode():
    gateway = DummyTextSourceGateway()
    gateway.set_execution_mode("async")

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    plan = usecase.plan_load("remote_source")
    assert plan.execution_mode == "async"


def test_load_failure():
    """测试加载文本失败。"""
    gateway = DummyTextSourceGateway()
    gateway.set_failure_result("网络错误")

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    result = usecase.load("any_key")
    assert not result.success
    assert result.error_message == "网络错误"


def test_load_from_clipboard_success():
    """测试从剪贴板加载成功。"""
    gateway = DummyTextSourceGateway()

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader("clipboard text"),
    )

    result = usecase.load_from_clipboard()
    assert result.success
    assert result.text == "clipboard text"


def test_load_from_clipboard_empty():
    """测试剪贴板为空。"""
    gateway = DummyTextSourceGateway()

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(""),
    )

    result = usecase.load_from_clipboard()
    assert not result.success
    assert "剪贴板无文本" in result.error_message
