import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import RegistryConfig
from src.backend.integration.ott_text_provider import OttTextProvider


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


def _make_provider(
    tmp_path: Path,
    responses: list,
    config: RegistryConfig | None = None,
) -> tuple[OttTextProvider, MagicMock]:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = responses
    provider = OttTextProvider(
        config or RegistryConfig(primary_url="https://ott.example.com"),
        tmp_path / "cache",
        http_client=client,
    )
    return provider, client


def test_get_catalog_prefers_ott_service_sources(tmp_path):
    provider, client = _make_provider(
        tmp_path,
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

    result = provider.get_catalog()

    assert [item.source_key for item in result] == ["poem"]
    assert result[0].label == "诗句"
    assert result[0].charCount == 12
    assert (
        client.get.call_args_list[0].args[0] == "https://ott.example.com/ott/v1/sources"
    )


def test_get_catalog_uses_static_sources_when_service_unavailable(tmp_path):
    provider, client = _make_provider(
        tmp_path,
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

    result = provider.get_catalog()

    assert [item.source_key for item in result] == ["static_poem"]
    assert (
        client.get.call_args_list[1].args[0] == "https://ott.example.com/sources.json"
    )


def test_get_catalog_falls_back_to_legacy_index(tmp_path):
    config = RegistryConfig(primary_url="https://ott.example.com")
    config.mirror_url = ""
    provider, client = _make_provider(
        tmp_path,
        [
            _mock_response(None, 404),
            _mock_response(None, 404),
            _mock_response(
                {
                    "sources": [
                        {
                            "id": 7,
                            "source_key": "legacy",
                            "label": "旧目录",
                            "charCount": 20,
                        }
                    ]
                }
            ),
        ],
        config,
    )

    result = provider.get_catalog()
    urls = [call.args[0] for call in client.get.call_args_list]

    assert result[0].source_key == "legacy"
    assert result[0].id == 7
    assert urls == [
        "https://ott.example.com/ott/v1/sources",
        "https://ott.example.com/sources.json",
        "https://ott.example.com/registry_index.json",
    ]
    assert all("/api/" not in url and "/ott-admin/" not in url for url in urls)


def test_get_catalog_tolerates_malformed_numeric_fields(tmp_path):
    provider, _client = _make_provider(
        tmp_path,
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

    result = provider.get_catalog()

    assert result[0].source_key == "bad_count"
    assert result[0].id == 1
    assert result[0].charCount == 0
