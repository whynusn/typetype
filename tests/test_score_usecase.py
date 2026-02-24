"""ScoreUseCase 测试。"""

from src.backend.application.usecases.score_usecase import ScoreUseCase
from src.backend.typing.score_data import ScoreData


class DummyClipboard:
    """用于复制测试的简易剪贴板对象。"""

    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


def _build_score_data() -> ScoreData:
    return ScoreData(
        time=10.0,
        key_stroke_count=30,
        char_count=20,
        wrong_char_count=2,
        date="2026-02-24 10:00:00",
    )


def test_build_score_message_with_empty_data():
    """空成绩数据应返回失败文案。"""
    assert ScoreUseCase.build_score_message(None) == "获取分数失败"


def test_build_score_message_with_data():
    """有成绩数据时应返回 HTML 摘要。"""
    score_data = _build_score_data()
    message = ScoreUseCase.build_score_message(score_data)
    assert "<b>" in message
    assert "速度:" in message


def test_copy_score_message():
    """复制时应写入摘要纯文本。"""
    score_data = _build_score_data()
    clipboard = DummyClipboard()

    ScoreUseCase.copy_score_message(score_data, clipboard)

    assert "速度:" in clipboard.value
    assert "准确率:" in clipboard.value


def test_build_history_record():
    """应按 QML 历史记录结构输出字典。"""
    score_data = _build_score_data()

    record = ScoreUseCase.build_history_record(score_data)

    assert set(record.keys()) == {
        "speed",
        "keyStroke",
        "codeLength",
        "wrongNum",
        "charNum",
        "time",
        "date",
    }
    assert record["charNum"] == 20
