"""OTT 分段测试：OttClient.get_segment 路由 + OttSegmentProvider 组合。

单实例 OttTextProvider 已删除，分段获取走 OttClient（Service Profile → Static
Profile）与 OttSegmentProvider（消费 fetch_ott_segment 接口的分片提供器）。
"""

import json
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import OttConfig
from src.backend.integration.ott_client import OttClient
from src.backend.integration.ott_segment_provider import OttSegmentProvider


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


def mock_text_response(text: str, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = text.encode("utf-8")
    response.text = text
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

    def fetch_text(cache_key, url, mirror_url, max_bytes):
        response = client.get(url)
        if response.status_code >= 400:
            return None
        return response.text

    provider = OttClient(
        primary_url="https://cdn.example.com",
        mirror_url="",
        authority="cdn.example.com",
        fetch_json=fetch_json,
        fetch_text=fetch_text,
        max_content_bytes=1_048_576,
    )
    return provider, client


def test_get_segment_returns_content():
    provider, _client = make_client(
        [
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
        ]
    )

    result = provider.get_segment("ent_1", "rev_1", 1)

    assert result is not None
    assert result["content"] == "分段正文"
    assert result["start_char"] == 0
    assert result["end_char"] == 4


def test_get_segment_uses_static_profile_text():
    provider, client = make_client(
        [mock_response(None, 404), mock_text_response("静态分段")]
    )

    result = provider.get_segment("book_1", "rev_static", 2)

    assert result is not None
    assert result["content"] == "静态分段"
    assert result["start_char"] == 1000
    assert result["end_char"] == 1004
    assert [call.args[0] for call in client.get.call_args_list] == [
        "https://cdn.example.com/ott/v1/entries/book_1/revisions/rev_static/segments/2",
        "https://cdn.example.com/segments/rev_static/2.txt",
    ]


def test_get_segment_uses_declared_static_segment_size():
    provider, _client = make_client(
        [mock_response(None, 404), mock_text_response("静态分段")]
    )

    result = provider.get_segment("book_1", "rev_static", 2, segment_size_hint=2000)

    assert result is not None
    assert result["start_char"] == 2000
    assert result["end_char"] == 2004
    assert result["content_hash"].startswith("sha256:")


class _FakeSegmentSource:
    """模拟 bridge 的 _FederationSegmentAdapter：暴露 fetch_ott_segment。"""

    def __init__(self, segments: dict) -> None:
        self._segments = segments

    def fetch_ott_segment(
        self, entry_id, revision_id, segment_index, source_segment_size=1000
    ):
        return self._segments.get(segment_index)


def test_ott_segment_provider_reads_server_segments():
    source = _FakeSegmentSource(
        {
            1: {"content": "AAAA", "index": 1},
            2: {"content": "BBBB", "index": 2},
            3: {"content": "CCCC", "index": 3},
        }
    )
    provider = OttSegmentProvider(
        source, "ent_1", "rev_1", total_chars=12, source_segment_size=4
    )

    assert provider.get_total_chars() == 12
    assert provider.get_segment(0, 4) == "AAAA"
    assert provider.get_segment(4, 4) == "BBBB"
    # 跨段读取：start=3 length=6 → "AAAABBBBCCCC"[3:9] == "ABBBBC"
    assert provider.get_segment(3, 6) == "ABBBBC"


def test_ott_segment_provider_clamps_to_total_chars():
    source = _FakeSegmentSource({1: {"content": "AAAA"}})
    provider = OttSegmentProvider(
        source, "ent_1", "rev_1", total_chars=4, source_segment_size=4
    )

    assert provider.get_segment(0, 100) == "AAAA"
    assert provider.get_segment(4, 4) == ""


def test_ott_segment_provider_raises_on_missing_segment():
    source = _FakeSegmentSource({})
    provider = OttSegmentProvider(
        source, "ent_1", "rev_1", total_chars=8, source_segment_size=4
    )

    try:
        provider.get_segment(0, 4)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "无法获取 OTT 分段" in str(exc)
