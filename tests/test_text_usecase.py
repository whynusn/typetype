from dataclasses import dataclass
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.config.text_source_config import SourceType
from src.backend.models.dto.fetched_text import FetchedText


@dataclass
class DummyTextSourceEntry:
    key: str
    label: str = ""
    source_type: SourceType = SourceType.LOCAL_PRACTICE
    local_path: str | None = None
    has_ranking: bool = False


class DummyTextSourceGateway:
    def __init__(self):
        self._success = True
        self._text = ""
        self._text_id = None
        self._error_message = ""
        self._source_entry: DummyTextSourceEntry | None = None

    def set_success_result(self, text: str, text_id: int | None = None):
        self._success = True
        self._text = text
        self._text_id = text_id

    def set_failure_result(self, error_message: str):
        self._success = False
        self._error_message = error_message

    def set_source_entry(self, source_entry: DummyTextSourceEntry):
        self._source_entry = source_entry

    def plan_load(self, source_key: str):
        if self._source_entry:
            return self._source_entry
        return DummyTextSourceEntry(key=source_key)

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


def test_load_non_ranking_local_text_does_not_request_server_text_id_lookup():
    gateway = DummyTextSourceGateway()
    gateway.set_source_entry(
        DummyTextSourceEntry(
            key="builtin_demo",
            label="本地示例",
            local_path="resources/texts/builtin_demo.txt",
            has_ranking=False,
        )
    )
    gateway.set_success_result("local text", text_id=None)
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    result = usecase.load(usecase.plan_load("builtin_demo"))

    assert result.success
    assert result.source_key == ""


def test_load_ranking_local_text_keeps_source_key_for_server_text_id_lookup():
    gateway = DummyTextSourceGateway()
    gateway.set_source_entry(
        DummyTextSourceEntry(
            key="fst_500",
            label="前五百",
            source_type=SourceType.LOCAL_RANKED,
            local_path="resources/texts/前五百.txt",
            has_ranking=True,
        )
    )
    gateway.set_success_result("local ranking text", text_id=None)
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(),
    )

    result = usecase.load(usecase.plan_load("fst_500"))

    assert result.success
    assert result.source_key == "fst_500"


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


def test_load_from_clipboard_removes_line_breaks_tabs_and_zero_width_chars():
    """普通剪贴板文本按 TypeSunny 规则去掉换行、Tab 和零宽字符。"""
    gateway = DummyTextSourceGateway()
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader("你\n好\r\t世\u200b界\ufeff"),
    )

    result = usecase.load_from_clipboard()

    assert result.success
    assert result.text == "你好世界"


def test_load_from_clipboard_extracts_body_from_sender_format():
    """发文格式只载入标题行和段号行之间的正文。"""
    gateway = DummyTextSourceGateway()
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(
            "[普(2.30)]标题 [字数4]\n正文一\n正文二\n-----第12段-测试"
        ),
    )

    result = usecase.load_from_clipboard()

    assert result.success
    assert result.text == "正文一正文二"


def test_load_from_clipboard_extracts_body_from_qingfawen_hyphen_mark():
    """晴发文 mark 可能含连字符，也应按发文格式提取正文。"""
    gateway = DummyTextSourceGateway()
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader(
            "[普(2.30)]晴发文标题 [字数5]\n晴发文正文\n-----第1-2段-晴发文"
        ),
    )

    result = usecase.load_from_clipboard()

    assert result.success
    assert result.text == "晴发文正文"


def test_load_from_clipboard_decodes_huangshu_sender_text():
    """标题以“皇叔 ”开头时，正文按 TypeSunny 的 UnicodeBias 解码。"""
    gateway = DummyTextSourceGateway()
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader("皇叔 标题\nbc\n-----第1段"),
    )

    result = usecase.load_from_clipboard()

    assert result.success
    assert result.text == "ab"


def test_load_from_clipboard_rejects_sender_format_without_body():
    """只有标题和段号行时不应载入空正文。"""
    gateway = DummyTextSourceGateway()
    usecase = LoadTextUseCase(
        text_gateway=gateway,
        clipboard_reader=DummyClipboardReader("标题\n-----第1段"),
    )

    result = usecase.load_from_clipboard()

    assert not result.success
    assert "剪贴板无文本" in result.error_message


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
