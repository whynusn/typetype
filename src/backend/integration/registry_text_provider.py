"""Backward-compatible import for the historical Registry provider name.

# deprecated: 仅兼容导入别名（RegistryTextProvider = OttTextProvider），新代码禁止 import；删除前需确认外部消费者
"""

from .ott_text_provider import OttTextProvider

RegistryTextProvider = OttTextProvider

__all__ = ["OttTextProvider", "RegistryTextProvider"]
