"""GenerateAiTextUseCase 测试。"""

from unittest.mock import MagicMock

from src.backend.application.usecases.generate_ai_text_usecase import (
    GenerateAiTextUseCase,
)


def _build_usecase(weak_chars=None):
    llm = MagicMock()
    llm.generate_text_stream.return_value = iter(["你好", "世界"])
    repo = MagicMock()
    if weak_chars is None:
        weak_chars = ["你", "好", "世"]
    stats = []
    for ch in weak_chars:
        s = MagicMock()
        s.char = ch
        stats.append(s)
    repo.get_chars_by_sort.return_value = stats
    return GenerateAiTextUseCase(llm_provider=llm, char_stats_repo=repo), llm, repo


def test_execute_returns_success_result():
    usecase, _, _ = _build_usecase()

    result = usecase.execute()

    assert result.success is True
    assert result.text == "你好世界"
    assert result.title == "AI 智能推荐"


def test_execute_passes_weak_chars_to_llm():
    usecase, llm, _ = _build_usecase(["天", "地"])

    usecase.execute()

    llm.generate_text_stream.assert_called_once_with(["天", "地"])


def test_execute_calls_on_chunk_callback():
    usecase, _, _ = _build_usecase()
    chunks: list[str] = []

    usecase.execute(on_chunk=chunks.append)

    assert chunks == ["你好", "世界"]


def test_execute_returns_error_when_no_weak_chars():
    usecase, llm, repo = _build_usecase(weak_chars=[])
    repo.get_chars_by_sort.return_value = []

    result = usecase.execute()

    assert result.success is False
    assert "打字数据" in result.error_message
    llm.generate_text_stream.assert_not_called()


def test_execute_returns_error_when_text_is_empty():
    usecase, llm, _ = _build_usecase()
    llm.generate_text_stream.return_value = iter([])

    result = usecase.execute()

    assert result.success is False
    assert "为空" in result.error_message


def test_execute_queries_error_rate_sort():
    usecase, _, repo = _build_usecase()

    usecase.execute()

    repo.get_chars_by_sort.assert_called_once_with(sort_mode="error_rate", n=20)


def test_execute_respects_weak_char_limit():
    usecase, _, repo = _build_usecase()

    usecase.execute(weak_char_limit=5)

    repo.get_chars_by_sort.assert_called_once_with(sort_mode="error_rate", n=5)
