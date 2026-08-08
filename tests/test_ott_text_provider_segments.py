from src.backend.config.runtime_config import RegistryConfig

from .ott_text_provider_helpers import (
    make_provider,
    make_provider_with_client,
    mock_response,
    mock_text_response,
)


def test_fetch_ott_segment_returns_content(tmp_path):
    provider = make_provider(
        tmp_path,
        responses=[
            mock_response(
                {
                    "entry_id": "ent_1",
                    "revision_id": "rev_1",
                    "index": 1,
                    "start_char": 0,
                    "end_char": 4,
                    "char_count": 4,
                    "content_hash": "sha256:abc",
                    "content": "分段正文",
                }
            )
        ],
    )

    result = provider.fetch_ott_segment("ent_1", "rev_1", 1)

    assert result is not None
    assert result["content"] == "分段正文"
    assert result["start_char"] == 0
    assert result["end_char"] == 4


def test_fetch_ott_segment_uses_static_profile_text(tmp_path):
    provider, client = make_provider_with_client(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
        [mock_response(None, 404), mock_text_response("静态分段")],
    )

    result = provider.fetch_ott_segment("book_1", "rev_static", 2)

    assert result is not None
    assert result["content"] == "静态分段"
    assert result["start_char"] == 1000
    assert result["end_char"] == 1004
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries/book_1/revisions/rev_static/segments/2",
        "https://cdn.example.com/segments/rev_static/2.txt",
    ]


def test_fetch_ott_segment_uses_declared_static_segment_size(tmp_path):
    provider = make_provider(
        tmp_path,
        RegistryConfig(primary_url="https://cdn.example.com", mirror_url=""),
        [mock_response(None, 404), mock_text_response("静态分段")],
    )

    result = provider.fetch_ott_segment(
        "book_1",
        "rev_static",
        2,
        source_segment_size=2000,
    )

    assert result is not None
    assert result["start_char"] == 2000
    assert result["end_char"] == 2004
    assert result["content_hash"].startswith("sha256:")
