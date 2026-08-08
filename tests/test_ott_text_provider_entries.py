from src.backend.config.runtime_config import RegistryConfig

from .ott_text_provider_helpers import (
    make_provider,
    make_provider_with_client,
    mock_response,
)


def test_fetch_text_by_entry_id_returns_ott_detail(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    result = provider.fetch_text_by_entry_id("ent_abc")

    assert result is not None
    assert result.content == "标准正文"
    assert result.entry_id == "ent_abc"
    assert result.revision_id == "rev_abc"
    assert result.content_mode == "inline"


def test_fetch_text_by_entry_id_accepts_non_ent_prefix(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    result = provider.fetch_text_by_entry_id("book_abc")

    assert result is not None
    assert result.entry_id == "book_abc"
    assert result.content == "正文"


def test_fetch_text_by_entry_id_ignores_legacy_content_shape(tmp_path):
    provider = make_provider(
        tmp_path,
        responses=[mock_response({"content": "旧格式", "title": "Legacy"})],
    )
    assert provider.fetch_text_by_entry_id("legacy") is None


def test_fetch_all_entries_prefers_ott_core_summary(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    assert provider.fetch_all_entries() == [
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


def test_fetch_all_entries_tolerates_malformed_numeric_fields(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    result = provider.fetch_all_entries()

    assert result[0]["entry_id"] == "ent_bad_count"
    assert result[0]["char_count"] == 0
    assert result[0]["segment_count"] == 0
    assert result[0]["segment_size_hint"] == 0


def test_fetch_all_entries_empty_ott_result_does_not_fallback_to_api(tmp_path):
    provider, client = make_provider_with_client(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
        [mock_response({"entries": [], "page": 1, "pages": 0, "total": 0})],
    )

    assert provider.fetch_all_entries() == []
    client.get.assert_called_once()
    assert "/ott/v1/entries" in client.get.call_args[0][0]


def test_fetch_all_entries_uses_static_profile_when_service_unavailable(tmp_path):
    provider, client = make_provider_with_client(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    result = provider.fetch_all_entries()

    assert len(result) == 1
    assert result[0]["entry_id"] == "book_1"
    assert result[0]["authority"] == "cdn.example.com"
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries?page=1&limit=200",
        "https://cdn.example.com/entries.json",
    ]


def test_fetch_text_by_entry_id_uses_static_profile_when_service_unavailable(tmp_path):
    provider, client = make_provider_with_client(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
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
        ],
    )

    result = provider.fetch_text_by_entry_id("book_1")

    assert result is not None
    assert result.content == "静态正文"
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries/book_1",
        "https://cdn.example.com/entries/book_1.json",
    ]
