from unittest.mock import MagicMock

import pytest

from src.backend.integration.wenlai_provider import (
    WenlaiAuthRequiredError,
    WenlaiProvider,
)
from src.backend.infrastructure.network_errors import NetworkTimeoutError
from src.backend.models.dto.wenlai_dto import (
    WenlaiCategory,
    WenlaiDifficulty,
    WenlaiText,
)


def test_wenlai_dtos_can_be_constructed():
    text = WenlaiText(
        title="书名",
        content="正文",
        mark="1-10",
        book_id=1,
        sort_num=2,
        end_sort_num=3,
        end_chars="尾",
        start_chars="头",
        category="wangwen",
        difficulty_level=4,
        difficulty_label="普",
        difficulty_score=2.34,
    )

    assert text.title == "书名"
    assert text.display_title == "[普(2.34)]书名"
    assert text.difficulty_text == "普(2.34)"
    assert text.progress_text == "2/10"
    assert text.sender_content == "[普(2.34)]书名 [字数2]\n正文\n-----第1-10段-晴发文"
    assert WenlaiDifficulty(id=4, name="普", count=10).name == "普"
    assert WenlaiCategory(code="wangwen", name="网文").code == "wangwen"


def test_wenlai_text_progress_falls_back_to_sort_num_when_mark_is_missing():
    text = WenlaiText(title="书名", content="正文", sort_num=8)

    assert text.progress_text == "8"


def test_wenlai_provider_parses_random_text_response():
    api_client = MagicMock()
    api_client.request.return_value = {
        "code": 200,
        "data": {
            "bookName": "测试书#meta",
            "content": "测试正文",
            "mark": "2-10",
            "bookId": 8,
            "sortNum": 2,
            "endSortNum": 3,
            "endChars": "尾",
            "startChars": "头",
            "category": "wangwen",
            "difficultyLevel": 4,
            "difficultyLabel": "普",
            "difficultyScore": 2.12,
        },
    }
    provider = WenlaiProvider(api_client, "https://example.test/", lambda: "token")

    text = provider.fetch_random_text(
        difficulty_level=4,
        length=500,
        strict_length=False,
        category="wangwen",
    )

    assert text.title == "测试书"
    assert text.content == "测试正文"
    assert text.mark == "2-10"
    assert text.book_id == 8
    assert text.sort_num == 2
    assert text.difficulty_label == "普"
    api_client.request.assert_called_once()
    _, url = api_client.request.call_args.args
    assert url == "https://example.test/api/texts/random"
    assert api_client.request.call_args.kwargs["params"] == {
        "difficultyLevel": 4,
        "length": 500,
        "strictLength": "false",
        "category": "wangwen",
    }
    assert api_client.request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer token"
    }


def test_wenlai_provider_omits_length_params_when_length_is_empty():
    api_client = MagicMock()
    api_client.request.return_value = {
        "code": 200,
        "data": {
            "bookName": "测试书",
            "content": "测试正文",
        },
    }
    provider = WenlaiProvider(api_client, "https://example.test/", lambda: "token")

    provider.fetch_random_text(
        difficulty_level=4,
        length=0,
        strict_length=True,
        category="wangwen",
    )

    assert api_client.request.call_args.kwargs["params"] == {
        "difficultyLevel": 4,
        "category": "wangwen",
    }


def test_wenlai_provider_fetches_next_segment_with_navigation_state():
    api_client = MagicMock()
    api_client.request.return_value = {
        "code": 200,
        "data": {
            "bookName": "书",
            "content": "下一段",
            "bookId": 1,
            "sortNum": 2,
        },
    }
    provider = WenlaiProvider(api_client, "https://example.test", lambda: "token")

    provider.fetch_adjacent_text(
        book_id=1,
        sort_num=1,
        direction="next",
        category="wangwen",
        end_sort_num=2,
        end_chars="尾",
        start_chars="",
        length=300,
        strict_length=True,
    )

    assert api_client.request.call_args.kwargs["params"] == {
        "bookId": 1,
        "sortNum": 1,
        "direction": "next",
        "category": "wangwen",
        "endSortNum": 2,
        "endChars": "尾",
        "length": 300,
        "strictLength": "true",
    }


def test_wenlai_provider_fetches_previous_segment_with_start_chars_only():
    api_client = MagicMock()
    api_client.request.return_value = {
        "code": 200,
        "data": {
            "bookName": "书",
            "content": "上一段",
            "bookId": 1,
            "sortNum": 1,
        },
    }
    provider = WenlaiProvider(api_client, "https://example.test", lambda: "token")

    provider.fetch_adjacent_text(
        book_id=1,
        sort_num=2,
        direction="prev",
        category="wangwen",
        end_sort_num=0,
        end_chars="",
        start_chars="头",
        length=0,
        strict_length=True,
    )

    assert api_client.request.call_args.kwargs["params"] == {
        "bookId": 1,
        "sortNum": 2,
        "direction": "prev",
        "category": "wangwen",
        "startChars": "头",
    }


def test_wenlai_provider_parses_difficulties_and_categories():
    api_client = MagicMock()
    api_client.request.side_effect = [
        {"code": 200, "data": {"levelStats": {"淼": 1, "普": 3}}},
        {
            "code": 200,
            "data": [
                {"code": "wangwen", "name": "网文", "isActive": True},
                {"code": "hidden", "name": "隐藏", "isActive": False},
            ],
        },
    ]
    provider = WenlaiProvider(api_client, "https://example.test", lambda: "token")

    difficulties = provider.get_difficulties()
    categories = provider.get_categories()

    assert [(d.id, d.name, d.count) for d in difficulties] == [
        (1, "淼", 1),
        (4, "普", 3),
    ]
    assert [(c.code, c.name) for c in categories] == [("wangwen", "网文")]


def test_wenlai_provider_raises_auth_error_on_401():
    api_client = MagicMock()
    api_client.request.return_value = {"code": 401, "msg": "未登录"}
    provider = WenlaiProvider(api_client, "https://example.test", lambda: "token")

    with pytest.raises(WenlaiAuthRequiredError):
        provider.fetch_random_text(
            difficulty_level=0,
            length=500,
            strict_length=False,
            category="",
        )


def test_wenlai_provider_reraises_api_client_last_error():
    api_client = MagicMock()
    api_client.request.return_value = None
    api_client.last_error = NetworkTimeoutError("timed out")
    provider = WenlaiProvider(api_client, "https://example.test", lambda: "token")

    with pytest.raises(NetworkTimeoutError, match="timed out"):
        provider.fetch_random_text(
            difficulty_level=0,
            length=500,
            strict_length=False,
            category="",
        )
