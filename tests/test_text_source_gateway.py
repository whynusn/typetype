from unittest.mock import MagicMock

from config.text_source_config import TextSourceEntry
from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.application.ports.local_text_loader import LocalTextLoader
from src.backend.application.ports.text_provider import TextProvider
from src.backend.config.runtime_config import RuntimeConfig


def _build_gateway(
    source: TextSourceEntry | None,
) -> tuple[TextSourceGateway, MagicMock, MagicMock, MagicMock]:
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source.return_value = source
    text_provider = MagicMock(spec=TextProvider)
    local_text_loader = MagicMock(spec=LocalTextLoader)
    gateway = TextSourceGateway(
        runtime_config=runtime_config,
        text_provider=text_provider,
        local_text_loader=local_text_loader,
    )
    return gateway, runtime_config, text_provider, local_text_loader


def test_get_execution_mode_for_local_source():
    gateway, _, _, _ = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )

    assert gateway.get_execution_mode("local") == "sync"


def test_get_execution_mode_for_remote_source():
    gateway, _, _, _ = _build_gateway(
        TextSourceEntry(key="remote", label="Remote", text_id="remote-id")
    )

    assert gateway.get_execution_mode("remote") == "async"


def test_get_execution_mode_raises_for_unknown_source():
    gateway, _, _, _ = _build_gateway(None)

    try:
        gateway.get_execution_mode("missing")
    except ValueError as exc:
        assert str(exc) == "未知文本来源(missing)"
    else:
        raise AssertionError("expected ValueError for missing source")


def test_load_text_by_key_uses_local_loader_for_local_source():
    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )
    local_text_loader.load_text.return_value = "local text"

    result = gateway.load_text_by_key("local")

    assert result == (True, "local text", "")
    runtime_config.get_text_source.assert_called_once_with("local")
    local_text_loader.load_text.assert_called_once_with("/tmp/text.txt")
    text_provider.fetch_text_by_key.assert_not_called()


def test_load_text_by_key_uses_text_provider_for_remote_source():
    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(key="remote", label="Remote", text_id="remote-id")
    )
    text_provider.fetch_text_by_key.return_value = "remote text"

    result = gateway.load_text_by_key("remote")

    assert result == (True, "remote text", "")
    runtime_config.get_text_source.assert_called_once_with("remote")
    text_provider.fetch_text_by_key.assert_called_once_with("remote")
    local_text_loader.load_text.assert_not_called()
