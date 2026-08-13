"""OttClient entry detail / 摘要路由测试（单实例 OttTextProvider 已删除）。

legacy content/{source_key}.json 回查与 fetch_all_entries 编排已移除，
此处直接验证 OttClient 的 Service Profile → Static Profile 路由与归一化。
"""

import json
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import OttConfig
from src.backend.integration.ott_client import OttClient


def mock_response(json_data, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.content = json.dumps(json_data).encode("utf-8") if json_data else b""
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def make_client(
    responses: list, config: "OttConfig | None" = None
) -> tuple[OttClient, MagicMock]:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = responses

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        response = client.get(url)
        if response.status_code >= 400:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    provider = OttClient(
        primary_url="https://cdn.example.com",
        mirror_url="",
        authority="cdn.example.com",
        fetch_json=fetch_json,
        fetch_text=lambda *args: None,
        max_content_bytes=config.max_content_bytes if config else 1_048_576,
    )
    return provider, client


def test_get_entry_returns_ott_detail():
    provider, _client = make_client(
        [
            mock_response(
                {
                    "entry_id": "ent_abc",
                    "source_key": "poem",
                    "title": "OTT 文章",
                    "content_mode": "inline",
                    "current_revision_id": "rev_abc",
                    "content_hash": "sha256:abc",
                    "content": "标准正文",
                }
            )
        ]
    )

    result = provider.get_entry("ent_abc")

    assert result is not None
    assert result["content"] == "标准正文"
    assert result["entry_id"] == "ent_abc"


def test_get_entry_accepts_non_ent_prefix():
    provider, _client = make_client(
        [
            mock_response(
                {
                    "entry_id": "book_abc",
                    "source_key": "book",
                    "title": "Book",
                    "content_mode": "inline",
                    "current_revision_id": "rev_book",
                    "content_hash": "sha256:book",
                    "content": "正文",
                }
            )
        ]
    )

    result = provider.get_entry("book_abc")

    assert result is not None
    assert result["entry_id"] == "book_abc"
    assert result["content"] == "正文"


def test_list_entries_normalizes_summary():
    provider, _client = make_client(
        [
            mock_response(
                {
                    "entries": [
                        {
                            "entry_id": "ent_1",
                            "source_key": "poem",
                            "title": "诗",
                            "preview": "一二三",
                            "char_count": 123,
                            "content_mode": "segmented",
                            "current_revision_id": "rev_1",
                            "segment_count": 2,
                            "segment_size_hint": 1000,
                        }
                    ],
                    "page": 1,
                    "pages": 1,
                }
            )
        ]
    )

    assert provider.list_entries() == [
        {
            "entry_id": "ent_1",
            "title": "诗",
            "preview": "一二三",
            "source_key": "poem",
            "source_label": "",
            "charCount": 123,
            "char_count": 123,
            "fetched_at": "",
            "category": "",
            "tags": [],
            "content_mode": "segmented",
            "current_revision_id": "rev_1",
            "segment_count": 2,
            "segment_size_hint": 1000,
            "authority": "cdn.example.com",
        }
    ]


def test_list_entries_tolerates_malformed_numeric_fields():
    provider, _client = make_client(
        [
            mock_response(
                {
                    "entries": [
                        {
                            "entry_id": "ent_bad_count",
                            "source_key": "poem",
                            "title": "坏数字",
                            "char_count": "oops",
                            "content_mode": "segmented",
                            "current_revision_id": "rev_bad_count",
                            "segment_count": "oops",
                            "segment_size_hint": "oops",
                        }
                    ],
                    "page": 1,
                    "pages": "oops",
                }
            )
        ]
    )

    result = provider.list_entries()

    assert result[0]["entry_id"] == "ent_bad_count"
    assert result[0]["char_count"] == 0
    assert result[0]["segment_count"] == 0
    assert result[0]["segment_size_hint"] == 0


def test_list_entries_empty_result_does_not_hit_legacy_endpoints():
    provider, client = make_client(
        [mock_response({"entries": [], "page": 1, "pages": 0, "total": 0})]
    )

    assert provider.list_entries() == []
    client.get.assert_called_once()
    assert "/ott/v1/entries" in client.get.call_args[0][0]
    assert "registry_index" not in client.get.call_args[0][0]


def test_list_entries_uses_static_profile_when_service_unavailable():
    provider, client = make_client(
        [
            mock_response(None, 404),
            mock_response(
                {
                    "entries": [
                        {
                            "entry_id": "book_1",
                            "source_key": "book",
                            "title": "静态书",
                            "preview": "开头",
                            "char_count": 2000,
                            "content_mode": "segmented",
                            "current_revision_id": "rev_static",
                            "segment_count": 2,
                            "segment_size_hint": 1000,
                        }
                    ],
                    "total": 1,
                }
            ),
        ]
    )

    result = provider.list_entries()

    assert len(result) == 1
    assert result[0]["entry_id"] == "book_1"
    assert result[0]["authority"] == "cdn.example.com"
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries?page=1&limit=200",
        "https://cdn.example.com/entries.json",
    ]


def test_get_entry_uses_static_profile_when_service_unavailable():
    provider, client = make_client(
        [
            mock_response(None, 404),
            mock_response(
                {
                    "entry_id": "book_1",
                    "source_key": "book",
                    "title": "静态书",
                    "content_mode": "inline",
                    "current_revision_id": "rev_static",
                    "content_hash": "sha256:static",
                    "content": "静态正文",
                }
            ),
        ]
    )

    result = provider.get_entry("book_1")

    assert result is not None
    assert result["content"] == "静态正文"
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries/book_1",
        "https://cdn.example.com/entries/book_1.json",
    ]
