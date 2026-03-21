"""TypingUseCase 测试。"""

from src.backend.application.usecases.typing_usecase import TypingUseCase
from src.backend.models.entity.session_stat import SessionStat


class DummyClipboard:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class DummyScoreGateway:
    def __init__(self, clipboard=None):
        self._clipboard = clipboard or DummyClipboard()

    def build_history_record(self, score_data):
        return {
            "speed": round(score_data.speed, 2),
            "keyStroke": round(score_data.keyStroke, 2),
            "codeLength": round(score_data.codeLength, 2),
            "wrongNum": score_data.wrong_char_count,
            "charNum": score_data.char_count,
            "time": round(score_data.time, 2),
            "date": score_data.date,
        }

    def build_score_message(self, score_data):
        if not score_data:
            return "获取分数失败"
        return f"<b>速度:</b> {score_data.speed:.2f}"

    def copy_score_to_clipboard(self, score_data):
        if not score_data:
            return
        self._clipboard.setText(f"速度: {score_data.speed:.2f}")


def _build_score_data() -> SessionStat:
    return SessionStat(
        time=10.0,
        key_stroke_count=30,
        char_count=20,
        wrong_char_count=2,
        date="2026-02-24 10:00:00",
    )


def test_build_score_message_with_empty_data():
    """空成绩数据应返回失败文案。"""
    usecase = TypingUseCase(score_gateway=DummyScoreGateway())
    assert usecase.build_score_message(None) == "获取分数失败"


def test_build_score_message_with_data():
    """有成绩数据时应返回 HTML 摘要。"""
    usecase = TypingUseCase(score_gateway=DummyScoreGateway())
    score_data = _build_score_data()
    message = usecase.build_score_message(score_data)
    assert "<b>" in message
    assert "速度:" in message


def test_copy_score_to_clipboard():
    """复制时应写入摘要纯文本。"""
    clipboard = DummyClipboard()
    gateway = DummyScoreGateway(clipboard=clipboard)
    usecase = TypingUseCase(score_gateway=gateway)
    score_data = _build_score_data()

    usecase.copy_score_to_clipboard(score_data)

    assert "速度:" in clipboard.value


def test_build_history_record():
    """应按 QML 历史记录结构输出字典。"""
    usecase = TypingUseCase(score_gateway=DummyScoreGateway())
    score_data = _build_score_data()

    record = usecase.build_history_record(score_data)

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
