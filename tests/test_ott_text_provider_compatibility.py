from src.backend.integration.ott_text_provider import OttTextProvider
from src.backend.integration.registry_text_provider import RegistryTextProvider


def test_registry_text_provider_remains_a_compatibility_alias() -> None:
    assert RegistryTextProvider is OttTextProvider
