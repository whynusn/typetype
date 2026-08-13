"""container.create_adapters 装配测试：跨层依赖注入验证。

覆盖：
- RegistryAdapter 持有注入的 runtime_config（不再穿透 federation 私有字段）
- TextAdapter 注入 FileSegmentProvider / InMemorySegmentProvider 实现类
- Adapters 束携带 OttSegmentProvider 类（Bridge 复用）
"""

from unittest.mock import MagicMock

from src.backend.config.container import (
    Adapters,
    Gateways,
    Infra,
    Providers,
    Repos,
    Services,
    UseCases,
    create_adapters,
)
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.integration.file_segment_provider import FileSegmentProvider
from src.backend.integration.in_memory_segment_provider import InMemorySegmentProvider
from src.backend.integration.ott_segment_provider import OttSegmentProvider


def _mock_bundles(runtime_config):
    infra = Infra(
        wenlai_api_client=MagicMock(),
        local_text_loader=MagicMock(),
        token_store=MagicMock(),
    )
    repos = Repos(local_article=MagicMock(), ziti=MagicMock(), trainer=MagicMock())
    providers = Providers(
        manifest_cache=MagicMock(),
        federation=MagicMock(),
        wenlai=MagicMock(),
        llm=MagicMock(),
    )
    gateways = Gateways(
        score=MagicMock(),
        text_source=MagicMock(),
        wenlai=MagicMock(),
        local_article=MagicMock(),
        ziti=MagicMock(),
        trainer=MagicMock(),
        typing_totals=MagicMock(),
        typing_history=MagicMock(),
    )
    use_cases = UseCases(
        load_text=MagicMock(),
        load_wenlai_text=MagicMock(),
        load_local_article_segment=MagicMock(),
        load_trainer_segment=MagicMock(),
        generate_ai_text=MagicMock(),
    )
    services = Services(
        char_stats=MagicMock(),
        typing=MagicMock(),
    )
    return infra, repos, providers, gateways, use_cases, services


def _build_adapters(runtime_config: RuntimeConfig) -> Adapters:
    infra, repos, providers, gateways, use_cases, services = _mock_bundles(
        runtime_config
    )
    return create_adapters(
        services, gateways, use_cases, providers, infra, runtime_config
    )


def test_create_adapters_wires_cross_layer_injections(monkeypatch):
    monkeypatch.setattr(
        "src.backend.integration.key_listener_factory.create_key_listener",
        lambda *a, **k: None,
    )
    runtime_config = RuntimeConfig()

    infra, repos, providers, gateways, use_cases, services = _mock_bundles(
        runtime_config
    )
    adapters = create_adapters(
        services, gateways, use_cases, providers, infra, runtime_config
    )

    # 项 6：RegistryAdapter 持有注入的 runtime_config（不再穿透 federation 私有字段）
    assert adapters.registry._runtime_config is runtime_config

    # 项 4/5：TextAdapter 注入 FileSegmentProvider / InMemorySegmentProvider 实现类
    assert adapters.text._file_segment_provider_cls is FileSegmentProvider
    assert adapters.text._in_memory_provider_cls is InMemorySegmentProvider

    # 项 2：container 装配一次 OttSegmentProvider 类，经 Adapters 束交给 Bridge 复用
    assert adapters.ott_segment_provider_cls is OttSegmentProvider

    # 联邦目录适配层持有注入的 federation / manifest_cache
    assert adapters.registry._federation is providers.federation
    assert adapters.registry._manifest_cache is providers.manifest_cache
