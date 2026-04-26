from unittest.mock import MagicMock

import pytest

from src.backend.application.usecases.load_wenlai_text_usecase import (
    LoadWenlaiTextUseCase,
)
from src.backend.config.runtime_config import WenlaiConfig
from src.backend.integration.wenlai_provider import WenlaiAuthRequiredError
from src.backend.models.dto.wenlai_dto import WenlaiText


def test_load_random_uses_runtime_config():
    gateway = MagicMock()
    gateway.is_logged_in.return_value = True
    gateway.config = WenlaiConfig(
        base_url="https://example.test",
        length=300,
        difficulty_level=4,
        category="wangwen",
        segment_mode="manual",
        strict_length=True,
    )
    gateway.fetch_random_text.return_value = WenlaiText(title="书", content="正文")
    usecase = LoadWenlaiTextUseCase(gateway)

    result = usecase.load_random()

    assert result.text.content == "正文"
    gateway.fetch_random_text.assert_called_once_with(
        difficulty_level=4,
        length=300,
        strict_length=True,
        category="wangwen",
    )


def test_load_random_requires_login():
    gateway = MagicMock()
    gateway.is_logged_in.return_value = False
    usecase = LoadWenlaiTextUseCase(gateway)

    with pytest.raises(WenlaiAuthRequiredError, match="请先在设置页登录晴发文"):
        usecase.load_random()


def test_load_adjacent_uses_current_segment_state_for_next():
    gateway = MagicMock()
    gateway.is_logged_in.return_value = True
    gateway.config = WenlaiConfig(length=200, strict_length=False)
    gateway.fetch_adjacent_text.return_value = WenlaiText(title="书", content="下一段")
    usecase = LoadWenlaiTextUseCase(gateway)
    current = WenlaiText(
        title="书",
        content="当前段",
        book_id=1,
        sort_num=5,
        end_sort_num=6,
        end_chars="尾",
        start_chars="头",
        category="wangwen",
    )

    result = usecase.load_adjacent(current, "next")

    assert result.text.content == "下一段"
    gateway.fetch_adjacent_text.assert_called_once_with(
        book_id=1,
        sort_num=5,
        direction="next",
        category="wangwen",
        end_sort_num=6,
        end_chars="尾",
        start_chars="",
        length=200,
        strict_length=False,
    )


def test_load_adjacent_rejects_invalid_direction():
    gateway = MagicMock()
    gateway.is_logged_in.return_value = True
    gateway.config = WenlaiConfig()
    usecase = LoadWenlaiTextUseCase(gateway)
    current = WenlaiText(title="书", content="当前段")

    with pytest.raises(ValueError, match="direction"):
        usecase.load_adjacent(current, "sideways")

    gateway.fetch_adjacent_text.assert_not_called()
