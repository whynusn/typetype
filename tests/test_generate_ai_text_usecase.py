"""GenerateAiTextUseCase 测试。"""

from unittest.mock import MagicMock, call

from src.backend.application.usecases.generate_ai_text_usecase import (
    GenerateAiTextUseCase,
)


def _make_chars(n):
    """构造 n 个 mock CharStat。"""
    stats = []
    for i in range(n):
        s = MagicMock()
        s.char = chr(0x4E00 + i)  # 从"一"开始的连续汉字
        stats.append(s)
    return stats


def _build_usecase(char_count=20):
    llm = MagicMock()
    llm.max_chars = 200
    llm.generate_text_stream.return_value = iter(["你好", "世界"])
    repo = MagicMock()
    repo.get_chars_by_sort.return_value = _make_chars(char_count)
    return GenerateAiTextUseCase(llm_provider=llm, char_stats_repo=repo), llm, repo


def test_execute_returns_success_result():
    usecase, _, _ = _build_usecase()

    result = usecase.execute()

    assert result.success is True
    assert result.text == "你好世界"
    assert result.title == "AI 智能推荐"


def test_execute_passes_weak_chars_to_llm():
    usecase, llm, _ = _build_usecase()

    usecase.execute(weak_char_limit=5)

    llm.generate_text_stream.assert_called_once()
    chars_arg = llm.generate_text_stream.call_args[0][0]
    assert len(chars_arg) == 5


def test_execute_calls_on_chunk_callback():
    usecase, _, _ = _build_usecase()
    chunks: list[str] = []

    usecase.execute(on_chunk=chunks.append)

    assert chunks == ["你好", "世界"]


def test_execute_returns_error_when_no_weak_chars():
    usecase, llm, repo = _build_usecase(char_count=0)
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


def test_execute_queries_recent_chars_first_then_fallback():
    usecase, _, repo = _build_usecase()

    usecase.execute(weak_char_limit=5)

    calls = repo.get_chars_by_sort.call_args_list
    assert len(calls) == 1  # 近 7 天足够，不会回退
    assert calls[0] == call(sort_mode="error_rate", n=15, recent_days=7)


def test_execute_falls_back_to_all_time_when_recent_insufficient():
    usecase, _, repo = _build_usecase(char_count=0)
    # 第一次（近 7 天）返回不足，第二次（全历史）返回足够
    repo.get_chars_by_sort.side_effect = [_make_chars(2), _make_chars(10)]

    usecase.execute(weak_char_limit=5)

    calls = repo.get_chars_by_sort.call_args_list
    assert len(calls) == 2
    assert calls[0] == call(sort_mode="error_rate", n=15, recent_days=7)
    assert calls[1] == call(sort_mode="error_rate", n=15)


def test_execute_returns_up_to_limit_chars():
    usecase, llm, _ = _build_usecase(char_count=20)

    usecase.execute(weak_char_limit=5)

    chars_arg = llm.generate_text_stream.call_args[0][0]
    assert len(chars_arg) == 5
