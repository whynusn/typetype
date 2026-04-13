from dataclasses import dataclass
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.models.dto.fetched_text import FetchedText


@dataclass
class DummyTextSourceEntry:
    key: str
    label: str = ""
    local_path: str | None = None


class DummyTextSourceGateway:
    def __init__(self):
        self._success = True
        self._text = ""
        self._text_id = None
        self._error_message = ""
        self._execution_mode = "sync"

    def set_success_result(self, text: str, text_id: int | None = None):
        self._success = True
        self._text = text
        self._text_id = text_id

    def set_failure_result(self, error_message: str):
        self._success = False
        self._error_message = error_message

    def set_execution_mode(self, execution_mode: str):
        self._execution_mode = execution_mode

    def plan_load(self, source_key: str):
        dummy_entry = DummyTextSourceEntry(key=source_key)
        if self._execution_mode == "sync":
            dummy_entry.local_path = "dummy/path.txt"
        return dummy_entry

    def load_from_plan(self, source):
        if self._success:
            return (True, FetchedText(content=self._text, text_id=self._text_id), "")
        return (False, None, self._error_message)


class DummyClipboardReader:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


def test_load_success():
    """测试成功加载文本。"""
    gateway = DummyTextSourceGateway()
    gateway.set_success_result("test text", text_id=123)

    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    plan = usecase.plan_load("any_key")
    result = usecase.load(plan)
    assert result.success
    assert result.text == "test text"
    assert result.text_id == 123


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

    plan = usecase.plan_load("any_key")
    result = usecase.load(plan)
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
    # 剪贴板文本不参与排行榜，text_id 为 None
    assert result.text_id is None


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
