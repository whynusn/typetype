from unittest.mock import MagicMock

from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.config.text_source_config import TextSourceEntry
from src.backend.models.dto.fetched_text import FetchedText
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


def test_load_from_plan_local_source_no_server_match():
    """本地文本在服务端无匹配时 text_id 为 None。"""
    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )
    local_text_loader.load_text.return_value = "local text"
    text_provider.fetch_text_by_client_id.return_value = None
    source = TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is True
    assert fetched is not None
    assert fetched.content == "local text"
    assert fetched.text_id is None
    assert error == ""
    local_text_loader.load_text.assert_called_once_with("/tmp/text.txt")


def test_load_from_plan_local_source_with_server_match():
    """本地文本 text_id 由 lookup_text_id 异步回查获得。"""
    gateway, runtime_config, text_provider, local_text_loader = _build_gateway(
        TextSourceEntry(
            key="builtin_demo", label="本地示例", local_path="/tmp/text.txt"
        )
    )
    local_text_loader.load_text.return_value = "你好，世界。"
    text_provider.fetch_text_by_client_id.return_value = None
    source = TextSourceEntry(
        key="builtin_demo", label="本地示例", local_path="/tmp/text.txt"
    )

    # load_from_plan 始终返回 text_id=None（不再同步回查）
    success, fetched, error = gateway.load_from_plan(source)
    assert success is True
    assert fetched is not None
    assert fetched.content == "你好，世界。"
    assert fetched.text_id is None

    # lookup_text_id 单独调用，回查服务端 text_id
    text_provider.fetch_text_by_client_id.return_value = FetchedText(
        content="你好，世界。", text_id=752
    )
    resolved = gateway.lookup_text_id("builtin_demo", "你好，世界。")
    assert resolved == 752


def test_load_from_plan_uses_text_provider_for_remote_source():
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
