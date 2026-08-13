"""OTT source catalog 测试：OttClient 协议路由（list_sources）。

单实例 OttTextProvider 已删除（ADR-013 决策 5），目录获取统一走
OttClient（federation 路径）。legacy registry_index.json fallback 已移除。
"""

import json
from unittest.mock import MagicMock

import httpx

from src.backend.integration.ott_client import OttClient


def _mock_response(json_data, status_code=200):
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


def _make_client(
    responses: list, authority: str = "ott.example.com"
) -> tuple[OttClient, MagicMock]:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = responses

    def fetch_json(cache_key, url, mirror_url, max_bytes):
        response = client.get(url)
        if response.status_code >= 400:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    ott = OttClient(
        primary_url="https://ott.example.com",
        mirror_url="",
        authority=authority,
        fetch_json=fetch_json,
        fetch_text=lambda *args: None,
        max_content_bytes=1_048_576,
    )
    return ott, client


def test_list_sources_prefers_service_sources():
    provider, client = _make_client(
        [
            _mock_response(
                {
                    "sources": [
                        {
                            "source_key": "poem",
                            "label": "诗句",
                            "description": "每日诗句",
                            "char_count": 12,
                            "category": "poem",
                        }
                    ]
                }
            )
        ],
    )

    sources = provider.list_sources()

    assert [s["source_key"] for s in sources] == ["poem"]
    assert sources[0]["label"] == "诗句"
    assert (
        client.get.call_args_list[0].args[0] == "https://ott.example.com/ott/v1/sources"
    )


def test_list_sources_uses_static_when_service_unavailable():
    provider, client = _make_client(
        [
            _mock_response(None, 404),
            _mock_response(
                {
                    "sources": [
                        {
                            "source_key": "static_poem",
                            "label": "静态诗句",
                            "char_count": 5,
                        }
                    ]
                }
            ),
        ],
    )

    sources = provider.list_sources()

    assert [s["source_key"] for s in sources] == ["static_poem"]
    assert (
        client.get.call_args_list[1].args[0] == "https://ott.example.com/sources.json"
    )


def test_list_sources_tolerates_malformed_numeric_fields():
    provider, _client = _make_client(
        [
            _mock_response(
                {
                    "sources": [
                        {
                            "id": "oops",
                            "source_key": "bad_count",
                            "label": "Bad Count",
                            "char_count": "oops",
                        }
                    ]
                }
            )
        ],
    )

    sources = provider.list_sources()

    assert sources[0]["source_key"] == "bad_count"
    assert sources[0]["id"] == 0
    assert sources[0]["char_count"] == 0
