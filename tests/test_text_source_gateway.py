from unittest.mock import MagicMock

from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.config.text_source_config import TextSourceEntry
from src.backend.ports.local_text_loader import LocalTextLoader
from src.backend.config.runtime_config import RuntimeConfig


def _build_gateway(
    source: TextSourceEntry | None,
) -> tuple[TextSourceGateway, MagicMock, MagicMock]:
    runtime_config = MagicMock(spec=RuntimeConfig)
    runtime_config.get_text_source.return_value = source
    local_text_loader = MagicMock(spec=LocalTextLoader)
    gateway = TextSourceGateway(
        runtime_config=runtime_config,
        local_text_loader=local_text_loader,
    )
    return gateway, runtime_config, local_text_loader


def test_plan_load_returns_source_entry():
    gateway, _, _ = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )

    source = gateway.plan_load("local")
    assert source.key == "local"
    assert source.local_path == "/tmp/text.txt"


def test_plan_load_raises_for_unknown_source():
    gateway, _, _ = _build_gateway(None)

    try:
        gateway.plan_load("missing")
    except ValueError as exc:
        assert str(exc) == "未知文本来源(missing)"
    else:
        raise AssertionError("expected ValueError for missing source")


def test_load_from_plan_local_source():
    """本地文本加载成功，text_id 恒为 None（无服务端回查）。"""
    gateway, runtime_config, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )
    local_text_loader.load_text.return_value = "local text"
    source = TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is True
    assert fetched is not None
    assert fetched.content == "local text"
    assert fetched.text_id is None
    assert error == ""
    local_text_loader.load_text.assert_called_once_with("/tmp/text.txt")
    runtime_config.get_text_source.assert_not_called()


def test_load_from_plan_missing_local_path():
    gateway, _, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local")
    )
    source = TextSourceEntry(key="local", label="Local")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is False
    assert fetched is None
    assert error == "本地来源缺少路径"
    local_text_loader.load_text.assert_not_called()


def test_load_from_plan_local_file_unreadable():
    gateway, _, local_text_loader = _build_gateway(
        TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")
    )
    local_text_loader.load_text.return_value = None
    source = TextSourceEntry(key="local", label="Local", local_path="/tmp/text.txt")

    success, fetched, error = gateway.load_from_plan(source)

    assert success is False
    assert fetched is None
    assert error == "无法读取本地文件"
