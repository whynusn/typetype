import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from src.backend.config.runtime_config import RegistryConfig
from src.backend.integration.ott_text_provider import OttTextProvider


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


def make_provider(
    tmp_path: Path,
    config: RegistryConfig | None = None,
    responses: list | None = None,
) -> OttTextProvider:
    provider, _client = make_provider_with_client(tmp_path, config, responses)
    return provider


def make_provider_with_client(
    tmp_path: Path,
    config: RegistryConfig | None = None,
    responses: list | None = None,
) -> tuple[OttTextProvider, MagicMock]:
    cfg = config or RegistryConfig(primary_url="https://cdn.example.com")
    client = MagicMock(spec=httpx.Client)
    if responses:
        if len(responses) == 1:
            client.get.return_value = responses[0]
        else:
            client.get.side_effect = responses
    return OttTextProvider(cfg, tmp_path / "registry_cache", http_client=client), client


def make_content_response(content: str = "缓存测试", title: str = "标题") -> dict:
    return {"content": content, "title": title, "text_id": 1}
