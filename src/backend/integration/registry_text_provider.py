"""Backward-compatible import for the historical Registry provider name."""

from .ott_text_provider import OttTextProvider

RegistryTextProvider = OttTextProvider

__all__ = ["OttTextProvider", "RegistryTextProvider"]
