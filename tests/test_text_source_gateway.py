from unittest.mock import MagicMock

from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.config.text_source_config import TextSourceEntry
from src.backend.ports.local_text_loader import LocalTextLoader
from src.backend.ports.text_provider import TextProvider
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


def test_plan_load_returns_sync_for_local_source():
    gateway, _, _, _ = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )

    source = gateway.plan_load("local")
    assert source.key == "local"
    assert source.local_path == "/tmp/text.txt"


def test_plan_load_returns_async_for_remote_source():
    gateway, _, _, _ = _build_gateway(TextSourceEntry(key="remote", label="Remote"))

    source = gateway.plan_load("remote")
    assert source.key == "remote"
    assert source.local_path is None


def test_plan_load_raises_for_unknown_source():
    gateway, _, _, _ = _build_gateway(None)

    try:
        gateway.plan_load("missing")
    except ValueError as exc:
        assert str(exc) == "未知文本来源(missing)"
    else:
        raise AssertionError("expected ValueError for missing source")


def test_load_from_plan_uses_local_loader_for_local_source():
    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )
    local_text_loader.load_text.return_value = "local text"
    source = TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is True
    assert fetched is not None
    assert fetched.content == "local text"
    # 本地文本不参与排行榜，text_id 为 None
    assert fetched.text_id is None
    assert error == ""
    # No repeated lookup for source entry since it's already in the plan
    runtime_config.get_text_source.assert_not_called()
    local_text_loader.load_text.assert_called_once_with("/tmp/text.txt")
    text_provider.fetch_text_by_key.assert_not_called()


def test_load_from_plan_uses_text_provider_for_remote_source():
    from src.backend.models.dto.fetched_text import FetchedText

    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(key="remote", label="Remote")
    )
    text_provider.fetch_text_by_key.return_value = FetchedText(
        content="remote text", text_id=789
    )
    source = TextSourceEntry(key="remote", label="Remote")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is True
    assert fetched is not None
    assert fetched.content == "remote text"
    # 客户端不再计算 hash，保留服务端返回的 text_id
    assert fetched.text_id == 789
    assert error == ""
    # No repeated lookup for source entry since it's already in the plan
    runtime_config.get_text_source.assert_not_called()
    text_provider.fetch_text_by_key.assert_called_once_with("remote")
    local_text_loader.load_text.assert_not_called()
