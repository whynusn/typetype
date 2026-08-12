"""Backward-compatible import for the historical Registry provider name.

# deprecated: 兼容导出（RegistryTextProvider = OttTextProvider），新代码用 ott_text_provider.OttTextProvider
"""

from .ott_text_provider import OttTextProvider

RegistryTextProvider = OttTextProvider

__all__ = ["OttTextProvider", "RegistryTextProvider"]
